# AI News Agent & Summarizer

Automated, LLM-based news reader. It monitors predefined RSS feeds (specifically for Israeli news), incrementally scrapes new articles throughout the day, avoids duplicates using a cloud database, and generates a concise, AI-powered daily digest delivered via email.

## 🚀 Key Features

* **Incremental Scraping:** Runs multiple times a day (morning, noon, afternoon) to spread the workload and capture breaking news.
* **Transactional Integrity:** Implements a "Safe Commit" system. Articles are only marked as "Processed" in the database *after* they have been successfully summarized. If the AI fails, the articles remain pending and are retried automatically on the next run.
* **Smart Deduplication:** Uses **Supabase (PostgreSQL)** to track every processed URL, ensuring no article is summarized twice.
* **Robust AI Integration:** Powered by **OpenAI's GPT-4o-mini** for high-quality, factual, and cost-effective summarization ($0.15/1M tokens).
* **Stealth Scraping:** Uses `Playwright` with stealth plugins to bypass bot detection on news sites.
* **Automated Reporting:** Aggregates all daily summaries into a clean HTML format and emails it, while also formatting it specifically for **Telegram delivery**.
* **Isolated Telegram Incremental:** Fetches public Telegram channels, tracking state reliably in **Supabase** for zero-loss message ingestion, and sends granular "News Flashes" (מבזקים) to your bot every 2 hours.
* **Serverless Architecture:** Hosted entirely on **GitHub Actions** using discrete workflows for Accumulation, Reporting, and Telegram parsing.

## 🧠 Algorithm & Workflow Logic

The bot operates in two distinct modes: **Accumulation** and **Reporting**.

### Phase 1: The Accumulation Algorithm (Runs 3x Daily)
*Goal: detailed processing of new articles with fail-safe logic.*

1.  **Initialize & Config:**
    * Load RSS feed URLs from `config.toml`.
    * Connect to Supabase DB and OpenAI using secrets.

2.  **Feed Parsing & Filtering:**
    * Fetch the latest XML data from all configured RSS feeds.
    * **Deduplication Check:** Query the `processed_articles` DB table for every link.
    * **Result:** A list of *only* new, unseen articles.

3.  **Content Extraction:**
    * Launch a headless Chromium browser (Playwright) with stealth headers.
    * Scrape the full text of valid articles.
    * **Output:** A structured dictionary of feed data (Links + Text), *without* saving to the DB yet.

4.  **Transactional Summarization (The Critical Step):**
    * The system takes the batch of new texts for a specific feed.
    * **Action:** Sends the text to **GPT-4o-mini** for summarization.
    * **Verification:**
        * ❌ **If AI Fails:** The process stops for this feed. Exceptions are logged. The articles are **NOT** marked as processed. They will be picked up again in the next run.
        * ✅ **If AI Succeeds:**
            1.  Save the generated summary to the `daily_summaries` table.
            2.  **COMMIT:** Iterate through the source URLs and insert them into the `processed_articles` table.

---

### Phase 2: The Telegram Incremental Algorithm (Runs Ev. 2 Hours)
*Goal: Fast, stateless parsing of real-time operational updates.*

1.  **State Retrieval:**
    * Queries the `telegram_state` table in Supabase to find the exact `datetime` of the last successfully processed message per channel.
2.  **Stateless Pagination:**
    * Fetches new messages from configured public Telegram channels (e.g., `yediotnews25`, `abualiexpress`), paginating completely dynamically until it reaches the stored timestamp.
3.  **LLM Compilation:**
    * Prompts the **GPT-5-Nano** model to act as a "News Flash Compiler", creating de-duplicated factual bullets of tactical events.
4.  **Delivery & State Commit:**
    * Formats the Markdown into Telegram-safe HTML and sends it directly to the user's Bot via the `sendMessage` API (chunking at 4000 characters to prevent API errors).
    * **Crucial:** Only if the message successfully sends does it save the new timestamps back to Supabase.

---

### Phase 2: The Reporting Algorithm (Runs 1x Evening)
*Goal: Synthesis and delivery of the daily digest.*

1.  **Data Retrieval:**
    * Query table `daily_summaries` in Supabase.
    * Select ALL summaries where `run_date` matches **Today**.

2.  **Master Synthesis:**
    * Concatenate all individual summaries into one large text block.
    * Send this block to **GPT-4o-mini** with a "newsletter generation" prompt.
    * The AI organizes the news by topic, removes redundancy, and formats it as Markdown.

3.  **Formatting & Delivery (Dual-Channel):**
    * Convert the AI Markdown output into a styled HTML email template and send via Gmail SMTP.
    * Concurrently format the AI Markdown into Telegram-compatible HTML and deploy it through the Telegram Bot API.

## ⚙️ GitHub Actions Architecture

The serverless scheduling is split into two discrete pipelines located in `.github/workflows/`:

1.  **`daily_news.yml`:**
    * Handles the heavy RSS scraping (Phase 1) at `08:00, 11:00, 14:00, 17:00 UTC`.
    * Triggers the Final Report (Phase 3) at `18:00 UTC` and deploys the dual Email/Telegram digest.
2.  **`telegram_news.yml`:**
    * Runs isolated on a `0 */2 * * *` cron (every 2 hours).
    * Passes the `-t yes` flag to trigger Phase 2 explicitly, ensuring RSS scraper slowness never delays operational flashes.

## 📂 Project Structure

```text
news_reader/
├── config/                  # Configuration files (Feed URLs, worker counts)
│   └── config.toml
├── main_process/            # Orchestration logic
│   └── process_all.py       # Implements the Transactional Algorithm
├── news_db/                 # Database interaction layer
│   └── db_manager.py        # Handles Supabase connections & Queries
├── llm_call_functions/      # AI Model logic
│   └── llm_call_open_ai.py  # OpenAI GPT-4o-mini wrapper (Tenacity + Retry)
├── rss_reader/              # Feed parsing logic
│   └── israel_rss_reader_v1.py
├── telegram_reader/         # Telegram channel public API integration
│   ├── telegram_reader.py   # Fetches and formatting
│   └── telegram_sender.py   # HTML conversion and Bot API sender
├── web_scrapper/            # Headless browser automation
│   └── scrapper_v2.py       # Playwright stealth scraper
├── email_sender/            # Email delivery system
├── prompts/                 # System prompts for the LLM
├── output/                  # Temporary local storage (for logs/HTML)
├── .streamlit/              # Local secrets storage
│   └── secrets.toml
├── .github/workflows/       # Automated Pipelines
│   ├── daily_news.yml       # RSS Scraping & Daily Digest pipeline
│   └── telegram_news.yml    # Incremental Telegram bot pipeline
├── main.py                  # Entry point (CLI via -s, -r, -t)
├── requirements.txt         # Python dependencies
└── README.md
