import feedparser
import toml as tomlib
import datetime
import time
import sys
import os
import calendar
import traceback
import ssl

# Ensure root is in path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_scrapper import scrapper_v2 as scrapper
from tqdm import tqdm
import concurrent.futures

# --- CONFIGURATION ---
# We use a helper function to get config safely
def get_config():
    try:
        with open("./config/config.toml", "r") as f:
            return tomlib.load(f)
    except Exception:
        # Fallback if path is slightly different
        with open("config/config.toml", "r") as f:
            return tomlib.load(f)

config_data = get_config()
MAX_WORKERS = config_data["process"]["workers"]

# WARNING: Bypass SSL verification
if not hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context
else:
    ssl._create_default_https_context = ssl._create_unverified_context


def _scrape_single_article(entry, start_date):
    """
    Core logic to scrape one article. Returns (url, text) or (None, None).
    """
    try:
        title = entry.get('title', 'No Title')
        if not entry.published_parsed:
            return None, None

        utc_timestamp = calendar.timegm(entry.published_parsed)
        published_time = datetime.datetime.fromtimestamp(
            utc_timestamp, datetime.timezone.utc
        )

        if published_time < start_date:
            return None, None

        # Scrape
        link = entry.get('link', 'No link')
        # print(f"[DEBUG] Scraping: {title}") # Optional: Comment out to reduce noise
        full_text = scrapper.get_full_article_text(link, print_every_step=False)

        if "Error:" in full_text:
            return None, None

        feed_url = entry.get('feed_url', 'Unknown Feed')
        summary = entry.get('summary', 'No summary available.')
        formatted_text = (
            f"Date: {published_time}. Title: {title}\nSummary: {summary}\n"
            f"Full text: {full_text}\n\n{'-' * 50}"
        )
        return feed_url, formatted_text

    except Exception as e:
        print(f"[ERROR] Failed {title}: {e}")
        return None, None


def get_text_for_llm(feeds, time_window=1):
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=time_window)
    print(f"Starting Process. Window: {time_window} days")

    # --- PHASE 1: PARSING ---
    entries_to_scrape = []
    for feed_url in tqdm(feeds, desc="Parsing Feeds", leave=False):
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                entry['feed_url'] = feed_url
                entries_to_scrape.append(entry)
        except Exception as e:
            print(f"Feed Error {feed_url}: {e}")

    if not entries_to_scrape:
        print("No articles found.")
        return "", 0

    print(f"Found {len(entries_to_scrape)} articles.")

    # --- PHASE 2: SCRAPING ---
    feed_text_map = {feed_url: [] for feed_url in feeds}
    total_scraped = 0

    # SMART SWITCH: Simple Loop vs ThreadPool
    if MAX_WORKERS <= 1:
        print("Running in SEQUENTIAL mode (Stable)...")
        for entry in tqdm(entries_to_scrape, desc="Scraping Sequentially"):
            feed_url, text = _scrape_single_article(entry, start_date)
            if feed_url and text:
                feed_text_map[feed_url].append(text)
                total_scraped += 1
    else:
        print(f"Running in PARALLEL mode ({MAX_WORKERS} workers)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(_scrape_single_article, e, start_date) for e in entries_to_scrape]
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Scraping Parallel"):
                try:
                    feed_url, text = future.result()
                    if feed_url and text:
                        feed_text_map[feed_url].append(text)
                        total_scraped += 1
                except Exception as e:
                    print(f"Future Error: {e}")

    print(f"Scraping Complete. Total: {total_scraped}")

    # --- PHASE 3: COMBINE ---
    all_summaries = []
    for feed_url in feeds:
        texts = feed_text_map[feed_url]
        if texts:
            all_summaries.append("\n\n".join(texts))

    return "\n\nXXX".join(all_summaries), total_scraped