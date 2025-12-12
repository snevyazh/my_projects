import feedparser
import toml as tomlib
import datetime
import sys
import os
import calendar
import ssl
from tqdm import tqdm
import concurrent.futures

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_scrapper import scrapper_v2 as scrapper
from news_db import db_manager


# ... (Config and SSL setup remains the same) ...
def get_config():
    try:
        with open("./config/config.toml", "r") as f:
            return tomlib.load(f)
    except Exception:
        with open("config/config.toml", "r") as f:
            return tomlib.load(f)


config_data = get_config()
MAX_WORKERS = config_data["process"]["workers"]

if not hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context
else:
    ssl._create_default_https_context = ssl._create_unverified_context


def _scrape_single_article(entry, start_date):
    """
    Checks DB -> Scrapes -> Returns Data (DOES NOT SAVE TO DB YET).
    """
    try:
        title = entry.get('title', 'No Title')
        link = entry.get('link', 'No link')

        # 1. CHECK DB: Still necessary to avoid scraping duplicates
        if db_manager.is_article_processed(link):
            return None

        if not entry.published_parsed:
            return None
        utc_timestamp = calendar.timegm(entry.published_parsed)
        published_time = datetime.datetime.fromtimestamp(
            utc_timestamp, datetime.timezone.utc
        )
        if published_time < start_date:
            return None

        # 2. SCRAPE
        full_text = scrapper.get_full_article_text(link, print_every_step=False)

        if "Error:" in full_text:
            return None

        # --- CHANGE: WE DO NOT SAVE TO DB HERE ANYMORE ---

        feed_url = entry.get('feed_url', 'Unknown Feed')
        summary = entry.get('summary', 'No summary available.')
        formatted_text = (
            f"Date: {published_time}. Title: {title}\nSummary: {summary}\n"
            f"Full text: {full_text}\n\n{'-' * 50}"
        )

        # Return a structured object
        return {
            "feed_url": feed_url,
            "text": formatted_text,
            "link": link,
            "title": title
        }

    except Exception as e:
        print(f"[Error] Failed {title}: {e}")
        return None


def get_text_for_llm(feeds, time_window=1):
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=time_window)
    print(f"Starting Process. Window: {time_window} days")

    # Phase 1: Parsing
    entries_to_scrape = []
    for feed_url in tqdm(feeds, desc="Parsing Feeds", leave=False):
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries:
                entry['feed_url'] = feed_url
                entries_to_scrape.append(entry)
        except Exception:
            pass

    if not entries_to_scrape:
        return {}, 0  # Return empty dict

    print(f"Found {len(entries_to_scrape)} potential articles. Checking DB...")

    # Phase 2: Scraping
    # Structure: { feed_url: { 'texts': [str], 'metadata': [(url, title)] } }
    feed_data = {url: {'texts': [], 'metadata': []} for url in feeds}
    total_scraped = 0

    def process_result(result):
        nonlocal total_scraped
        if result:
            f_url = result['feed_url']
            if f_url in feed_data:
                feed_data[f_url]['texts'].append(result['text'])
                feed_data[f_url]['metadata'].append((result['link'], result['title']))
                total_scraped += 1

    if MAX_WORKERS <= 1:
        for entry in tqdm(entries_to_scrape, desc="Processing Articles"):
            res = _scrape_single_article(entry, start_date)
            process_result(res)
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(_scrape_single_article, e, start_date) for e in entries_to_scrape]
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures), desc="Processing"):
                try:
                    process_result(future.result())
                except Exception:
                    pass

    print(f"New articles scraped: {total_scraped}")

    # Return the structured dictionary, not a string
    return feed_data, total_scraped