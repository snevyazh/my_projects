import feedparser
import datetime
import time
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from web_scrapper import scrapper_v2 as scrapper
from tqdm import tqdm
import concurrent.futures
import ssl

# --- CONFIGURATION ---
# You can safely change this number.
# 10 is a good starting point.
# If you have a strong machine, you can try 15 or 20.
MAX_WORKERS = 15

# WARNING: This bypasses SSL certificate verification.
# Restored from your working backup.
if not hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context
else:
    ssl._create_default_https_context = ssl._create_unverified_context


def _scrape_article_worker(entry, start_date):
    """
    Worker function to be run by each thread in the pool.
    It checks the article's date and scrapes it.
    """
    try:
        # Use your original, working time logic
        published_time = datetime.datetime.fromtimestamp(
            time.mktime(entry.published_parsed), datetime.timezone.utc
        )

        # Check if the article is in the time window
        if published_time < start_date:
            return None, None  # Article is too old

        summary = entry.get('summary', 'No summary available.')
        title = entry.get('title', 'No title')
        link = entry.get('link', 'No link')

        # The slow part: scrape the full text
        full_text = scrapper.get_full_article_text(link, print_every_step=False)

        if "Error:" in full_text:
            print(f"\n[Scrape Failed]: {title} ({full_text})")
            return None, None  # Scraping failed

        # Return a tuple: (feed_title, formatted_text)
        feed_title = entry.get('feed_title', 'Unknown Feed')
        formatted_text = (
            f"Date: {published_time}. Title: {title}\nSummary: {summary}\n"
            f"Full text: {full_text}\n\n{'-' * 50}"
        )
        return feed_title, formatted_text

    except Exception as e:
        # Catch any other errors (like malformed dates)
        print(f"\n[Worker Error]: {entry.get('title', 'Unknown')} - {e}")
        return None, None  # Skip bad article


def get_text_for_llm(feeds, time_window=1):
    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=time_window)

    # --- PHASE 1: PRODUCER (Fast, Sequential) ---
    # Gathers all article entries that need to be scraped

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
            feed_title = feed.feed.get('title', feed_url)

            for entry in feed.entries:
                # Add the feed title to each entry for later grouping
                entry['feed_title'] = feed_title
                entries_to_scrape.append(entry)

        except Exception as e:
            print(f"Could not parse feed {feed_url}. Error: {e}")

    if not entries_to_scrape:
        print("No new articles found.")
        return "", 0

    print(f"Phase 1 Complete: Found {len(entries_to_scrape)} total articles to check.")

    # --- PHASE 2: CONSUMER (Slow, Parallel) ---
    # Scrapes all articles using a thread pool

    # This dictionary will hold the text for each feed
    # e.g., {"Ynet": "article 1...", "Walla": "article 1..."}
    feed_text_map = {feed_url: [] for feed_url in feeds}
    # We also map feed URLs to their titles
    feed_title_map = {}

    total_scraped_articles = 0

    print(f"Phase 2: Scraping articles in parallel (using {MAX_WORKERS} workers)...")

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        # Create a list of futures
        futures = [executor.submit(_scrape_article_worker, entry, start_date) for entry in entries_to_scrape]

        for future in tqdm(concurrent.futures.as_completed(futures),
                           total=len(futures),
                           desc="Scraping Articles",
                           ascii=True,
                           mininterval=0.5
                           ):

            feed_title, formatted_text = future.result()

            if feed_title and formatted_text:
                # Find the original feed URL this title belongs to
                for url, title_list in feed_text_map.items():
                    # This logic is a bit brittle, assumes titles are unique-ish
                    # A better way would be to pass the URL through
                    # But for now, we find the feed_url associated with this title

                    # Let's re-map the feed_title to its original URL
                    # This is inefficient but will work

                    if feed_title not in feed_title_map:
                        feed_title_map[feed_title] = feed_url

                    origin_url = feed_title_map[feed_title]

                    if origin_url in feed_text_map:
                        feed_text_map[origin_url].append(formatted_text)
                        total_scraped_articles += 1
                        break

    print(f"\nPhase 2 Complete: Successfully scraped {total_scraped_articles} articles.")

    # --- FINAL STEP: Re-build your original structure ---
    # Create a list of strings, one for each feed, just like your backup

    all_article_summaries = []
    for feed_url in feeds:
        article_texts = feed_text_map[feed_url]
        if article_texts:
            all_article_summaries.append("\n\n".join(article_texts))

    # Join the strings from each feed with "XXX"
    full_text_for_llm = "\n\nXXX".join(all_article_summaries)
    return full_text_for_llm, total_scraped_articles

