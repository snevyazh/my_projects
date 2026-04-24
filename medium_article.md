# Probabilistic Revenue Forecasting: Combining Survival Analysis with Revenue Efficiency Curves

How we forecast 10+ years of account revenue by separating "how much" from "how long" — across multiple independent revenue streams

---

## 1. The Problem

We needed to forecast account-level revenue across **multiple independent revenue streams** — SaaS subscription fees, transaction-based processing revenue, foreign exchange revenue from cross-border payments, and others. Each stream has its own driver metric and its own trajectory. They can be consumed independently or aggregated into a single lifetime value figure.

The business horizon is long: deal valuation and strategic planning require forecasts of **10 or more years**, not one or two. And the accounts we need to forecast are heterogeneous: some are brand new with no history at all, others are six months in and still finding their footing, and the mature ones have a stable multi-year trend we can extrapolate directly.

Standard tools break in this setting. ARIMA needs per-account time series, but most accounts don't have three years of clean history. Neural networks become unstable when extrapolating five times beyond the training window on small per-account datasets. Prophet doesn't generalize cleanly across accounts with different activation points and wildly different scale. We needed something that could handle a day-one account and a five-year veteran in the same system.

The solution we landed on is a **separation of concerns design**: split the forecast into what an account would earn if active, and how likely it is to remain active — and multiply the two.

---

## 2. The Core Design: Separation of Concerns

The key architectural insight is to decouple two independent questions:

- **Revenue pipeline:** *What would this account earn per quarter if it stays active?*
- **Survival pipeline:** *What is the probability the account is still active in quarter N?*

The final output is their product:

```text
PROBABILISTIC_REVENUE = REVENUE × SURVIVAL
```

This represents the **expected value** of revenue in each future quarter — accounting for churn risk without conflating it with revenue trajectory.

```text
Stream 1 (Subscription)  ──► REVENUE_1 ──╮
Stream 2 (Transactions)  ──► REVENUE_2 ──┤
Stream 3 (FX/Cross-border)──► REVENUE_3 ──┤ × SURVIVAL ──► PROBABILISTIC_REVENUE
          ...                             ┤
Stream N                 ──► REVENUE_N ──╯

Survival Pipeline ──────────────────────────► SURVIVAL (shared across all streams)
```

Each revenue stream is modeled independently — it has its own driver, its own cluster structure, its own efficiency curve. Survival is shared: whether an account churns is a property of the account, not of any individual revenue stream.

This design has a clean operational property: **churn handling lives in exactly one place**. When you investigate an anomaly or tune the system, the revenue and survival sides can be diagnosed independently. The revenue column continues to reflect the account's earning potential even after it churns — the survival multiplier is what drives probabilistic revenue to zero, making the mechanism transparent.

---

## 3. Revenue Forecasting — Revenue Efficiency Curves

### 3a. The Revenue Efficiency Metric

For each revenue stream, we compute an **efficiency ratio**: revenue divided by its driver metric. For cross-border FX revenue, the driver is cross-border payment volume. For transaction-based revenue, it's transaction count. For SaaS subscriptions, it's the active invoice or seat count.

```python
# Step 3: Calculate efficiency metric (revenue / driver)
efficiency_column = f"{stream.upper()}_EFFICIENCY"

stream_data[efficiency_column] = stream_data[revenue_column] / stream_data.apply(
    lambda x: calculate_driver_value(x, config_data, stream), axis=1
)

# Remove infinite/NaN efficiency values (zero-driver months)
stream_data = stream_data[np.isfinite(stream_data[efficiency_column])].copy()
```

This normalization does something important: it removes scale. A large enterprise and a small startup can share the same efficiency trajectory shape even though their absolute revenues are orders of magnitude apart. That means we can pool accounts into clusters and estimate a shared curve per cluster — which is the next step.

For mature accounts with a long, stable history, we skip the efficiency machinery and extrapolate directly from the observed revenue trend. The efficiency curve framework is most critical for **new and developing accounts** that don't have enough personal history and need to borrow trajectory shape from similar peers.

### 3b. DTW Clustering — Grouping by Trajectory Shape

The goal is to group accounts whose efficiency evolves similarly over time. The challenge is that accounts activate at different calendar dates, have different amounts of history, and may start and ramp at different speeds. A naive feature-based clustering would ignore the temporal dynamics entirely.

We use **Dynamic Time Warping (DTW)** to measure trajectory distance. DTW is elastic — it can align two sequences that have similar shapes but different timing. An account that ramped to plateau in 8 quarters and one that ramped in 12 quarters are "close" under DTW even if they'd be far apart under Euclidean distance.

On top of DTW, we apply **recursive binary splitting** using account attributes (company tier, industry segment, product type, revenue size, and engineered features from raw attributes). At each split step, we try all available feature splits, choose the one that minimizes within-group DTW distance, and stop when groups become too small. The output is a decision tree stored as a JSON rule set — which is exactly what we use at inference time to assign a new account to a cluster:

```python
def classify_account_safe(
    account_features: dict,
    cluster_rules: list[list[dict]]
) -> int:
    """
    Find the first cluster whose rules are all satisfied by the account.
    Returns cluster index, or -1 if no match (caller handles fallback).
    """
    for i, rules in enumerate(cluster_rules):
        # All rules within a cluster are AND-ed
        if all(_check_rule_safe(account_features, rule) for rule in rules):
            return i
    return -1


def _check_rule_safe(account_features: dict, rule: dict) -> bool:
    feature, op, rule_value = rule['feature'], rule['op'], rule['value']
    account_value = account_features.get(feature)

    if account_value is None or pd.isna(account_value):
        return False

    if op == '==':
        return str(account_value) == str(rule_value)
    if op == '!=':
        return str(account_value) != str(rule_value)
    if op in ['<=', '>']:
        try:
            acc_num, rule_num = float(account_value), float(rule_value)
            return acc_num <= rule_num if op == '<=' else acc_num > rule_num
        except (ValueError, TypeError):
            return False
    return False
```

The rule-based design is worth emphasising: anyone in finance or business operations can read a JSON rule set and understand *why* a given account landed in its cluster. That interpretability matters enormously when the system informs multi-year deal valuations.

### 3c. Curve Fitting per Cluster

Once we have clusters, we compute the average efficiency trajectory per cluster and fit one of two mathematical models:

- **Logistic (S-curve):** `L / (1 + exp(-k(x - x₀)))` — for clusters still ramping up. L is the plateau efficiency, k is growth steepness, x₀ is the inflection quarter.
- **Exponential decay:** `a·exp(-b·x) + c` — for clusters that have plateaued or are declining. a is the initial amplitude, b is the decay rate, c is the long-run asymptote.

Selection is automatic: if the smoothed final efficiency exceeds 95% of the smoothed peak, the cluster is still growing and we use logistic. Otherwise, exponential decay.

```python
# Select model based on trajectory shape
if smoothed_final > threshold_mult * smoothed_max:
    model_to_use = logistic_func
    model_type = "logistic"

    L_min = max_efficiency * bounds_mult.get('L_min', 1.0)
    L_max = max_efficiency * bounds_mult.get('L_max', 1.5)
    k_min = bounds_mult.get('k_min', 0.2)
    bounds = ([L_min, k_min, x0_min], [L_max, k_max, x0_max])

else:
    model_to_use = exponential_decay
    model_type = "exponential_decay"

    c_min = max(final_efficiency * c_min_mult, max_efficiency * 0.5)
    c_max = max_efficiency  # asymptote bounded by observed peak

    # a >= -c_min ensures f(x) = a·exp(-b·x) + c >= 0 for all x >= 0
    bounds = ([-c_min, 0, c_min], [np.inf, np.inf, c_max])

popt, _ = curve_fit(
    model_to_use, x_post_activation, y_post_activation,
    p0=guess, bounds=bounds, maxfev=50000
)
```

The **domain-informed bounds are not optional**. On small cluster datasets, `scipy.optimize.curve_fit` is free to find mathematically valid but economically nonsensical parameter values — large negative amplitudes, near-zero decay constants, plateau values above anything ever observed. Adding bounds encodes domain knowledge: efficiency cannot go negative, the long-run asymptote cannot exceed the observed peak, growth rate must be non-trivial. Bounds turn an unconstrained optimization problem into a tractable one.

After fitting, we enforce a **plateau**: from a configured ordinal quarter onward, efficiency is capped at the fitted curve's value at that quarter. This prevents curves from continuing to grow or oscillate unrealistically at 10+ year horizons where we have no empirical grounding.

### 3d. Account Maturity Segmentation

How we apply the cluster curve depends on how much history an account has:

- **New accounts** (very few quarters of history): no personal trend is stable enough — use the cluster curve entirely.
- **Developing accounts** (moderate history): a hybrid — weighted average of the account's own observed efficiency and the cluster baseline. Not enough history for a reliable personal trend, but enough to inform and adjust the cluster prior.
- **Mature accounts** (stable multi-year history): extrapolate directly from the account's own historical trend. At this point, borrowing from the cluster would add noise, not signal.

### 3e. VIP Accounts — The Generalization Dilemma

Some accounts are structural outliers: large enough or unusual enough that no cluster meaningfully represents them. They cannot be grouped with peers because there are no meaningful peers. But their revenue must still appear in total LTV.

The competing concerns here are real: (1) we must include them, (2) we absolutely cannot generalize them. Every VIP account is volatile in its own specific way.

Our solution: **per-account individual curves with manually tunable parameters**, bounded within a range of the last known value. No cluster assignment, no peer borrowing. These accounts are mature by definition — the dilemma is that generalization would be actively harmful, so we remove it from the equation entirely.

---

## 4. Survival Analysis — Log-Rank Clustering + Kaplan-Meier

### 4a. Account Status Tracking

Account status — onboarding, live, on-hold, low-activity, cancelled, churned — is tracked monthly as part of standard business operations. The pipeline receives these monthly status records as input. Active states include onboarding, live, on-hold, and low-activity variants. Terminal states are cancellation (failed to go live) and churn (lost a live customer).

Monthly records are aggregated to quarters before feeding the survival model: terminal statuses take precedence within a quarter, and the most recent monthly status is used otherwise.

### 4b. Why Log-Rank Test for Clustering?

An arbitrary k-means on account features might produce groups that are feature-different but have identical churn patterns. We want groups with **statistically different survival curves**.

We use the **log-rank test** as the splitting criterion in recursive binary splitting: at each node, try every available feature split (company tier, industry segment, product type, revenue size), pick the split with the lowest log-rank p-value, and stop when p ≥ 0.05 or the group becomes too small. The result is a survival cluster tree where every branch represents a group whose churn behavior is statistically distinguishable from its sibling.

A generalized example of what this produces:

```text
All Accounts
    ├── Company Tier == "Enterprise"?  (p < 0.001)
    │       ├── Industry == "Fintech"?  (p = 0.003) → Cluster 1 (High retention)
    │       └── Otherwise              → Cluster 2 (Med-high retention)
    └── Company Tier != "Enterprise"
            ├── Industry == "E-commerce"?  (p = 0.012) → Cluster 3 (Medium retention)
            └── Otherwise
                    ├── Revenue ≤ $10K/mo?  (p = 0.045) → Cluster 4 (Low-medium)
                    └── Revenue > $10K/mo   → Cluster 5 (Low retention)
```

### 4c. Kaplan-Meier Estimation

Within each survival cluster, we fit a **Kaplan-Meier model**:

```text
S(t) = ∏ᵢ [(nᵢ - dᵢ) / nᵢ]
```

where nᵢ is the number of accounts at risk entering period i and dᵢ is the number of churns during period i. The product runs across all observed ordinal periods up to t.

Kaplan-Meier handles **censoring naturally**: accounts that are still active at our observation cutoff contribute to the risk set up to that point without being counted as churns. This is important because at any given snapshot, most accounts in a mature cohort are still live.

### 4d. Extrapolation to 10+ Years

Observed survival data typically covers 3–5 years. The forecast horizon is 10+ years. We need to extrapolate.

We try two models in sequence. The primary is a **Gaussian with offset**:

```text
f(t) = a·exp(-(t - b)² / (2c²)) + d
```

If that fit fails, we fall back to a **stretched exponential**:

```text
f(t) = a·exp(-(kt)^β) + c
```

Both capture the characteristic shape of survival curves: fast early decay, then a slower long tail as the surviving cohort grows increasingly stable.

We also enforce a **survival floor**: the extrapolated curve cannot fall below `last_known_rate × floor_multiplier`. Without a floor, the mathematical curve can drive survival toward zero faster than business reality supports. The intuition behind the floor is well-grounded: accounts that have survived several years have demonstrated a materially lower churn risk than newly acquired ones. Veteran accounts exhibit habit and stickiness. The floor encodes that domain knowledge as a hard constraint.

### 4e. Override with Actuals

For accounts with observed history, we don't use the model's absolute values — we use the **model's decay rate** and anchor it to reality.

```python
# For each quarter beyond the last observed actual:
curve_decay_rate = original_forecast[t] / original_forecast[t - 1]

# Check if curve has reached plateau (near-zero slope)
decay_amount = abs(1 - curve_decay_rate)

if decay_amount < plateau_threshold:
    # Plateau: apply a small fixed annual decay
    forecast[t] = forecast[t - 1] * quarterly_decay
else:
    # Not on plateau: apply the curve's proportional decay rate
    forecast[t] = forecast[t - 1] * curve_decay_rate
```

For the observed historical quarters: if the account churned, survival is set to 0 for all subsequent periods. If the account was active, survival is set to 1.0 — we know it was alive, the model's absolute value is irrelevant.

The rate-preserving formula `S(t) = (pred_t / pred_{t-1}) × S(t-1)` means the transition from observed data (ending at 1.0 for a live account) to the model's decay is smooth. There's no artificial step-down from 1.0 to the model's year-four value at the moment actuals run out.

---

## 5. Combining the Two Pipelines

The output is a **long-format events table**: one row per (account, ordinal quarter, revenue stream).

| Ordinal Quarter | Revenue | Survival | Probabilistic Revenue | Prediction Type |
| --- | --- | --- | --- | --- |
| Q1 | $5,000 | 1.000 | $5,000 | actual |
| Q2 | $8,000 | 1.000 | $8,000 | actual |
| Q4 | $15,000 | 0.950 | $14,250 | hybrid |
| Q8 | $24,000 | 0.740 | $17,760 | hybrid |
| Q40 | $50,000 | 0.420 | $21,000 | extrapolation |

`PROBABILISTIC_REVENUE = REVENUE × SURVIVAL` — stored as an integer for downstream aggregation.

The `PREDICTION_TYPE` column provides a **full audit trail**: actual, cluster-based prediction, hybrid, or extrapolation. A downstream analyst can filter to only high-confidence rows, or aggregate across all types to get total LTV. Historical pipeline runs are preserved; an `IS_CURRENT` flag marks the latest prediction so only one run surfaces in the default view.

The revenue column at Q40 shows $50,000 — the account's projected earning potential. The probabilistic revenue shows $21,000 — the expected value after accounting for a 58% chance the account has churned by then. Both numbers are useful in different contexts.

---

## 6. Sale-Time Predictions — Validating at the Moment of Deal Close

For each account we also run a **sale-time prediction**: a separate forecast using only the revenue drivers that were available at the time of deal close. What did sales know at that moment — company size, product selection, estimated volumes — and what would we have predicted based solely on that information?

This prediction is stored in separate columns on the same rows as the ongoing forecast.

The value is retrospective: as time passes, we can compare the sale-time prediction against actuals and against the current (updated) forecast. Were we systematically over-estimating cross-border volumes at deal time? Were certain product types consistently mis-predicted? The comparison surfaces patterns that feed back into sales process calibration.

One practical challenge: the driver inputs available at deal close can be rough estimates. Sales teams estimate future volumes based on conversations and assumptions, not observed data. The quality of the sale-time prediction is therefore bounded by the quality of those inputs — an important modeling consideration that is worth tracking separately from the model's ongoing accuracy.

---

## 7. Production Architecture

The system runs as a **SageMaker Pipeline** on a monthly cadence:

```text
Data Warehouse → Training Step → Artifact Storage → Inference Step → Data Warehouse
                  (per stream)    (JSON rules +       (per stream)    (events table)
                                   formulas per
                                    cluster)
```

Training produces two artifacts per stream: a **cluster assignment rule set** (a JSON decision tree mapping account features to cluster index) and **cluster efficiency formulas** (fitted curve parameters per cluster). Both are stored to S3.

Inference loads these artifacts, assigns each account to its cluster, applies the appropriate curve (or hybrid, or per-account VIP formula), multiplies by survival, and writes the events table back to the data warehouse. All historical runs are preserved; only the latest is flagged as current.

All tunable parameters live in a **TOML configuration file** — forecast horizon in ordinal quarters, maturity thresholds, plateau enforcement quarter, survival floor multiplier, blending weights for hybrid accounts, IQR multipliers for outlier filtering. Tuning the model does not require a code change.

Streams can be consumed independently downstream — the subscription stream's LTV can be reported without FX — or summed into a total account LTV view.

---

## 8. Key Lessons

**Separate concerns.** Centralizing churn in the survival pipeline makes the revenue pipeline simpler. When an anomaly appears in probabilistic revenue, the first diagnostic question is always: is it the revenue side or the survival side? A clean separation makes that question answerable immediately.

**Bound your curve fitters.** Unconstrained `scipy.optimize.curve_fit` on sparse cluster data finds mathematically valid but economically nonsensical solutions. Large negative amplitudes, degenerate asymptotes, unrealistic growth rates — all are possible if you don't constrain the parameter space with domain knowledge. Always add bounds. The constraint `a >= -c` for an exponential decay `a·exp(-b·x) + c` is the difference between a non-negative forecast and a negative one.

**Floors and caps are features, not hacks.** The survival floor, plateau enforcement, growth caps — each one encodes something real about how B2B revenue behaves over long horizons. Veteran accounts don't churn at the same rate as new ones. Efficiency curves don't grow indefinitely. Treating these constraints as engineering compromises misses the point: they're domain knowledge made explicit.

**Maturity segmentation is structural.** A single model for all accounts ignores a fundamental difference: a new account has essentially no personal signal, a three-year veteran has a stable trend. Treating them the same either over-generalizes mature accounts (noisy) or over-personalizes new ones (unstable). The three-tier segmentation — cluster-only, hybrid blend, personal extrapolation — is a recognition that the right information source changes as the account matures.

**Interpretability compounds.** Rule-based cluster assignments are explainable to finance, to business operations, to the sales team. A finance analyst can trace exactly why an account received the forecast it did: it matched these rules, landed in this cluster, and used this curve. When stakeholders trust the mechanism, the model gets used. When they distrust it, the output gets ignored regardless of accuracy — and you never get the feedback needed to improve it.

---

*This system is one approach to a genuinely hard problem. The core ideas — efficiency normalization, DTW trajectory clustering, logistic vs. decay curve selection, log-rank survival segmentation, rate-preserving actuals override — generalize well beyond any single industry or revenue model. If you're building something similar, the biggest practical lesson is to start with the separation of concerns: get revenue and survival into independent pipelines before worrying about anything else.*
