# AI News Agent & Summarizer

This project is a fully automated, database-backed news agent. It monitors predefined RSS feeds (specifically for Israeli news), incrementally scrapes new articles throughout the day, avoids duplicates using a cloud database, and generates a concise, AI-powered daily digest delivered via email.

## 🚀 Key Features

* **Incremental Scraping:** Runs multiple times a day (morning, noon, afternoon) to spread the workload and capture breaking news.
* **Smart Deduplication:** Uses **Supabase (PostgreSQL)** to track every processed URL, ensuring no article is summarized twice.
* **Robust AI Integration:** Powered by **OpenAI's GPT-4o-mini** for high-quality, factual, and cost-effective summarization ($0.15/1M tokens).
* **Stealth Scraping:** Uses `Playwright` with stealth plugins to bypass bot detection on news sites.
* **Automated Reporting:** Aggregates all daily summaries into a clean, mobile-friendly HTML report and emails it every evening.
* **Zero-Maintenance:** Hosted entirely on **GitHub Actions** with scheduled workflows.

## 🧠 Algorithm & Workflow Logic

The bot operates in two distinct modes: **Accumulation** and **Reporting**.

### Phase 1: The Accumulation Algorithm (Runs 3x Daily)
*Goal: detailed processing of new articles without sending incomplete reports.*

1.  **Initialize & Config:**
    * Load RSS feed URLs from `config.toml`.
    * Connect to Supabase DB using secrets.
    * Initialize the OpenAI client.

2.  **Feed Parsing:**
    * Fetch the latest XML data from all configured RSS feeds.
    * Extract article Links, Titles, and Publication Dates.
    * **Filter:** Discard articles older than the defined time window (e.g., 24 hours).

3.  **Deduplication (The Critical Step):**
    * For every potential article link:
        * **Query DB:** Check table `processed_articles` for the URL.
        * **Decision:**
            * **Found?** $\rightarrow$ SKIP (Stop processing this item).
            * **Not Found?** $\rightarrow$ PROCEED to scraping.

4.  **Content Extraction:**
    * Launch a headless Chromium browser (Playwright) with stealth headers.
    * Navigate to the URL and handle cookie banners/popups.
    * Extract the main body text using `trafilatura`.

5.  **Micro-Summarization:**
    * Send the raw article text to **GPT-4o-mini** with a strict "factual summary" system prompt.
    * Receive a concise summary paragraph.

6.  **Persistence:**
    * **Step A:** Insert the URL into `processed_articles` (preventing future re-scraping).
    * **Step B:** Insert the summary text + timestamp into `daily_summaries`.

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

3.  **Formatting & Delivery:**
    * Convert the AI Markdown output into a styled HTML email template.
    * Connect to Gmail SMTP server.
    * Send the email to the subscriber list.

## 📂 Project Structure

```text
news_reader/
├── config/                  # Configuration files (Feed URLs, worker counts)
│   └── config.toml
├── main_process/            # Orchestration logic
│   └── process_all.py       # Implements the Algorithm described above
├── news_db/                 # Database interaction layer
│   └── db_manager.py        # Handles Supabase connections & Queries
├── llm_call_functions/      # AI Model logic
│   └── llm_call.py          # OpenAI GPT-4o-mini wrapper (Tenacity + Retry)
├── rss_reader/              # Feed parsing logic
│   └── israel_rss_reader_v1.py
├── web_scrapper/            # Headless browser automation
│   └── scrapper_v2.py       # Playwright stealth scraper
├── email_sender/            # Email delivery system
├── prompts/                 # System prompts for the LLM
├── output/                  # Temporary local storage (for logs/HTML)
├── .streamlit/              # Local secrets storage
│   └── secrets.toml
├── .github/workflows/       # Automation instructions
│   └── daily_news.yml
├── main.py                  # Entry point (CLI)
├── requirements.txt         # Python dependencies
└── README.md