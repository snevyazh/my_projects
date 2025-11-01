import feedparser
import datetime
import time
import scrapper_v2 as scrapper
from tqdm import tqdm

import ssl

# WARNING: This bypasses SSL certificate verification.
ssl._create_default_https_context = ssl._create_unverified_context


def get_text_for_llm(feeds, time_window=1):

    now = datetime.datetime.now(datetime.timezone.utc)
    start_date = now - datetime.timedelta(days=time_window)

    all_article_summaries = []

    for feed_url in tqdm(feeds,
                    total=len(feeds),
                    position=0,
                    ncols=100
                    ):
        try:
            # Parse the feed URL
            feed_articles_summary = []
            feed = feedparser.parse(feed_url)
            # print(f"Checking Feed: {feed.feed.title}, URL: {url}")

            for entry in feed.entries[:2]: ##### TODO remove:

                # Get the publish date and make it timezone-aware
                published_time = datetime.datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), datetime.timezone.utc
                )

                # Check if the article is from the last 24 hours
                if published_time >= start_date:
                    # 'summary' is the key field you want for your LLM
                    summary = entry.get('summary', 'No summary available.')
                    title = entry.get('title', 'No title')
                    link = entry.get('link', 'No link')

                    full_text = scrapper.get_full_article_text(link)

                    # Add the title and summary to feed texts list
                    feed_articles_summary.append(f"Date: {published_time}. "
                                                 f"Title: {title}\nSummary: {summary}\n"
                                                 f"Full text: {full_text}\n\n{'-' * 50}")
            # add feed text to overall list
            all_article_summaries.append('\n\n'.join(feed_articles_summary))

        except Exception as e:
            print(f"Could not parse feed {feed_url}. Error: {e}")


    # This is the final text
    full_text_for_llm = "\n\nXXX".join(all_article_summaries)
    return full_text_for_llm, len(all_article_summaries)




