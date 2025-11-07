import feedparser
import datetime
import time
from web_scrapper import scrapper_v2 as scrapper
from tqdm import tqdm

def get_text_for_llm(feeds, time_window=1):
    # Set our time window (e.g., last 24 hours)
    now = datetime.datetime.now(datetime.timezone.utc)
    one_day_ago = now - datetime.timedelta(days=time_window)

    all_article_summaries = []

    for url in tqdm(feeds,
                    total=len(feeds),
                    position=0,
                    ncols=100
                    ):
        try:
            # Parse the feed URL
            feed = feedparser.parse(url)

            # print(f"Checking Feed: {feed.feed.title}, URL: {url}")

            for entry in feed.entries:
                # Get the publish date and make it timezone-aware
                published_time = datetime.datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), datetime.timezone.utc
                )

                # Check if the article is from the last 24 hours
                if published_time >= one_day_ago:
                    # 'summary' is the key field you want for your LLM
                    summary = entry.get('summary', 'No summary available.')
                    title = entry.get('title', 'No title')
                    link = entry.get('link', 'No link')

                    full_text = scrapper.get_full_article_text(link)

                    # Add the title and summary to our list for the LLM
                    all_article_summaries.append(f"Date: {published_time}. "
                                                 f"Title: {title}\nSummary: {summary}\n"
                                                 f"Full text: {full_text}\n\n{'-' * 50}")

        except Exception as e:
            print(f"Could not parse feed {url}. Error: {e}")


    # This is the final text you will send to the LLM
    full_text_for_llm = "\n\nXXX".join(all_article_summaries)
    return full_text_for_llm, len(all_article_summaries)




