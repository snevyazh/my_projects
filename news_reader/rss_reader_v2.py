import feedparser
import datetime
import time
import scrapper_v2 as scrapper


# from tqdm import tqdm # No longer needed

def get_text_for_llm(feeds, time_window=1, st_status=None, st_progress=None):
    """
    Fetches article text from RSS feeds within a given time window.

    Now includes optional Streamlit elements to report progress.
    """
    # Set our time window (e.g., last 24 hours)
    now = datetime.datetime.now(datetime.timezone.utc)
    one_day_ago = now - datetime.timedelta(days=time_window)

    all_article_summaries = []
    total_feeds = len(feeds)

    # Replaced tqdm with a standard loop
    for i, url in enumerate(feeds):

        feed_title = "Unknown Feed"
        try:
            # Update Streamlit status
            if st_status:
                st_status.text(f"Processing feed {i + 1}/{total_feeds}...")
            if st_progress:
                st_progress.progress((i + 1) / total_feeds)

            # Parse the feed URL
            feed = feedparser.parse(url)
            feed_title = feed.feed.title

            # Removed the inner tqdm loop for entries
            for entry in feed.entries:
                # Get the publish date and make it timezone-aware
                published_time = datetime.datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), datetime.timezone.utc
                )

                # Check if the article is from the last 24 hours
                if published_time >= one_day_ago:
                    summary = entry.get('summary', 'No summary available.')
                    title = entry.get('title', 'No title')
                    link = entry.get('link', 'No link')

                    # Scrape the full text
                    full_text = scrapper.get_full_article_text(link)

                    # Add the title and summary to our list for the LLM
                    all_article_summaries.append(f"Date: {published_time}. "
                                                 f"Title: {title}\nSummary: {summary}\n"
                                                 f"Full text: {full_text}\n\n{'-' * 50}")

                    # Give a little feedback on the most recent article
                    if st_status:
                        st_status.text(f"Feed {i + 1}/{total_feeds}: Fetched '{title}'")


        except Exception as e:
            print(f"Could not parse feed {url} ({feed_title}). Error: {e}")
            if st_status:
                st_status.warning(f"Could not parse feed: {feed_title}. Skipping.")

    # This is the final text you will send to the LLM
    full_text_for_llm = "\n\nXXX".join(all_article_summaries)
    return full_text_for_llm, len(all_article_summaries)
