import feedparser
import toml as tomlib
import datetime
import time
import sys
import os
import calendar
import traceback  # For detailed error logging

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_scrapper import scrapper_v2 as scrapper
from tqdm import tqdm
import concurrent.futures
import ssl

# --- CONFIGURATION ---
with open("./config/config.toml", "r") as f:
    config_data = tomlib.load(f)
MAX_WORKERS = config_data["process"]["workers"]

# WARNING: This bypasses SSL certificate verification.
if not hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context
else:
    ssl._create_default_https_context = ssl._create_unverified_context


def _scrape_article_worker(entry, start_date):
    """
    Worker function to be run by each thread in the pool.
    """
    try:
        title = entry.get('title', 'No Title')

        if not entry.published_parsed:
            print(f"\n[DEBUG] SKIPPED (No Date): {title}")
            return None, None

        utc_timestamp = calendar.timegm(entry.published_parsed)
        published_time = datetime.datetime.fromtimestamp(
            utc_timestamp, datetime.timezone.utc
        )

        # Check if the article is in the time window
        if published_time < start_date:
            # This is not an error, just filtering. We'll hide it.
            # print(f"\n[DEBUG] SKIPPED (Too Old): {title}")
            return None, None  # Article is too old

        # --- If it's not too old, we try to scrape ---
        print(f"\n[DEBUG] ATTEMPTING: {title}")

        link = entry.get('link', 'No link')
        full_text = scrapper.get_full_article_text(link, print_every_step=False)

        if "Error:" in full_text:
            print(f"\n[DEBUG] SCRAPE FAILED: {title} ({full_text})")
            return None, None  # Scraping failed

        feed_url = entry.get('feed_url', 'Unknown Feed')
        summary = entry.get('summary', 'No summary available.')
        formatted_text = (
            f"Date: {published_time}. Title: {title}\nSummary: {summary}\n"
            f"Full text: {full_text}\n\n{'-' * 50}"
        )

        print(f"\n[DEBUG] SUCCESS: Scraped {title}")
        return feed_url, formatted_text

    except Exception as e:
        print(f"\n[WORKER CRASH]: {title} - {e}")
        traceback.print_exc()
        return None, None  # Skip bad article


def get_text_for_llm(feeds, time_window=1):
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=time_window)
    print(f"Process starting. Time window (UTC): {start_date} to {now}")

    # --- PHASE 1: PRODUCER (Fast, Sequential) ---
    print("Phase 1: Parsing RSS feeds to find articles...")
    entries_to_scrape = []

    for feed_url in tqdm(feeds,
                         desc="Parsing Feeds     ",
                         ascii=True,
                         mininterval=1.0,
                         leave=False
                         ):
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                entry['feed_url'] = feed_url
                entries_to_scrape.append(entry)
        except Exception as e:
            print(f"Could not parse feed {feed_url}. Error: {e}")

    if not entries_to_scrape:
        print("No new articles found.")
        return "", 0

    print(f"Phase 1 Complete: Found {len(entries_to_scrape)} total articles to check.")

    # --- PHASE 2: CONSUMER (Slow, Parallel) ---
    feed_text_map = {feed_url: [] for feed_url in feeds}
    total_scraped_articles = 0

    print(f"Phase 2: Scraping articles in parallel (using {MAX_WORKERS} workers)...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(_scrape_article_worker, entry, start_date) for entry in entries_to_scrape]

        for future in tqdm(concurrent.futures.as_completed(futures),
                           total=len(futures),
                           desc="Scraping Articles",
                           ascii=True,
                           mininterval=0.5
                           ):

            feed_url, formatted_text = future.result()

            if feed_url and formatted_text:
                if feed_url in feed_text_map:
                    feed_text_map[feed_url].append(formatted_text)
                    total_scraped_articles += 1
                else:
                    print(f"\n[Worker Warning]: Got article from unexpected feed: {feed_url}")

    print(f"\nPhase 2 Complete: Successfully scraped {total_scraped_articles} articles.")

    # --- FINAL STEP: Re-build your original structure ---
    all_article_summaries = []
    for feed_url in feeds:
        article_texts = feed_text_map[feed_url]
        if article_texts:
            all_article_summaries.append("\n\n".join(article_texts))

    full_text_for_llm = "\n\nXXX".join(all_article_summaries)
    return full_text_for_llm, total_scraped_articles