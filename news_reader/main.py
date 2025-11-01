import israel_rss_reader
from datetime import datetime
from custom_functions import count_tokens
import llm_call
import install_browsers
import time
import toml as tomlib
import os

# 1. check and install playwright
install_browsers.check_and_install_playwright_browsers()


# A list of reliable, real-time Hebrew news feeds
ISRAELI_NEWS_FEEDS = [
    "https://www.ynet.co.il/Integration/StoryRss1854.xml",  # Ynet - Main News
    # "https://rss.walla.co.il/feed/22",  # Walla! - Main News
    # "https://www.maariv.co.il/rss/breakingnews",  # Maariv - Breaking News
    # "https://www.haaretz.co.il/rss/1.600",  # Haaretz - Main News
    # "https://www.israelhayom.co.il/rss.xml",
    # "https://www.mako.co.il/rss/news-israel.xml"
]
# set the env
with open("./.streamlit/secrets.toml", "r") as f:
    config_data = tomlib.load(f)
os.environ["GEMINI_API_KEY"] = config_data["secrets"]["GEMINI_API_KEY"]
print("key", os.getenv("GEMINI_API_KEY"))

# 2. Run the feed reader
full_text_for_llm, articles_num = israel_rss_reader.get_text_for_llm(feeds=ISRAELI_NEWS_FEEDS,
                                                 time_window=1)
print(f"Collected {articles_num} articles for the LLM digest.")
print(f"Text tokens number is {count_tokens(full_text_for_llm)}")

# save results of summarization
run_time = datetime.today().strftime('%Y-%m-%d')
with open(f"./output/full_text_{run_time}.txt", 'w') as f:
    f.write(full_text_for_llm)

# run LLM
text_by_stream = full_text_for_llm.split("XXX")

with open("./prompts/prompt_first_summary.md", 'r') as f:
    prompt_template_1 = f.read()

feeds_summaries = []

model = llm_call.get_model()

for text in text_by_stream:
    prompt_feed = prompt_template_1.format(text)
    answer_for_feed = llm_call.call_llm(model, prompt_feed)
    time.sleep(60)
    feeds_summaries.append(answer_for_feed)

summaries_text = "\n\n".join(feeds_summaries)

with open(f"./output/summary_texts_feeds_{run_time}.txt", 'w') as f:
    f.write(summaries_text)

# summarize the final text
with open("./prompts/prompt_second_summary.md", 'r') as f:
    prompt_template_2 = f.read()
prompt_final = prompt_template_1.format(summaries_text)
answer_final = llm_call.call_llm(model, prompt_final)

with open(f"./output/summary_text_{run_time}.txt", 'w') as f:
    f.write(answer_final)




