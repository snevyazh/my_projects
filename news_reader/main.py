import warnings
# suppress warnings
warnings.filterwarnings('ignore')
import israel_rss_reader as israel_rss_reader # or backup for old version
from datetime import datetime
# from custom_functions import count_tokens
import llm_call
import install_browsers
import time
import toml as tomlib
import os
import sys


# 1. check and install playwright
install_browsers.check_and_install_playwright_browsers()

# real-time Hebrew news feeds
with open("./config/config.toml", "r") as f:
    config_data = tomlib.load(f)
ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]

# set the env
with open("./.streamlit/secrets.toml", "r") as f:
    config_data = tomlib.load(f)
os.environ["GEMINI_API_KEY"] = config_data["secrets"]["GEMINI_API_KEY"]

# Set default time window
time_window = 1
if len(sys.argv) > 1:
    try:
        # Read time_window from the first argument
        time_window = int(sys.argv[1])
    except ValueError:
        print(f"Invalid time window argument '{sys.argv[1]}'. Using default: {time_window} day(s).")
else:
    print(f"No time window specified. Using default: {time_window} day(s).")
#

# 2. Run the feed reader
full_text_for_llm, articles_num = israel_rss_reader.get_text_for_llm(
                                                feeds=ISRAELI_NEWS_FEEDS,
                                                time_window=time_window)
print(f"Collected {articles_num} articles for the LLM digest, Sir.")
# print(f"Text tokens number is {count_tokens(full_text_for_llm)}")

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




