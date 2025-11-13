import os
import sys
import time

# We are in the root folder, so paths are simpler
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
import warnings
import markdown  # NEW: Import Markdown library for conversion

# suppress warnings
warnings.filterwarnings('ignore')
from rss_reader import israel_rss_reader_v1 as israel_rss_reader
from datetime import datetime
from custom_functions.custom_functions import count_tokens
from llm_call_functions import llm_call as llm_call
from web_scrapper import install_browsers
import toml as tomlib

# 1. check and install playwright
install_browsers.check_and_install_playwright_browsers()

# real-time Hebrew news feeds
with open("./config/config.toml", "r") as f:
    config_data = tomlib.load(f)
ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]
workers = config_data["process"]["workers"]

# set the env
with open("./.streamlit/secrets.toml", "r") as f:
    secret_data = tomlib.load(f)
os.environ["GEMINI_API_KEY"] = secret_data["secrets"]["GEMINI_API_KEY"]
os.environ["OPENAI_API_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]

# Set default time window
time_window = 1
if len(sys.argv) > 1:
    try:
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

# save results of summarization
run_time = datetime.today().strftime('%Y-%m-%d')
output_file_path = f"./output/full_text_{run_time}.txt"
try:
    with open(output_file_path, 'w') as f:
        f.write(full_text_for_llm)
    print(f"Successfully saved full text to {output_file_path}")
except Exception as e:
    print(f"Error writing full text file: {e}")

if articles_num == 0:
    print("No articles found. Exiting.")
    sys.exit()

# run LLM
text_by_stream = full_text_for_llm.split("XXX")

with open("./prompts/prompt_first_summary.md", 'r') as f:
    prompt_template_1 = f.read()

feeds_summarIES = []

model = llm_call.get_model()

# --- Simplified Loop (No Chunking) ---
print(f"Processing {len(text_by_stream)} feeds...")
for i, text in enumerate(text_by_stream):
    if not text.strip():
        continue

    chunk_token_count = count_tokens(text)
    print(f"  - Calling LLM for feed {i + 1}/{len(text_by_stream)} (approx. {chunk_token_count:.0f} tokens)...")
    prompt_feed = prompt_template_1.format(text)

    answer_for_feed = llm_call.call_llm(model, prompt_feed)

    if answer_for_feed:
        feeds_summarIES.append(answer_for_feed)
    else:
        print(f"    - Feed {i + 1} FAILED to summarize after retries.")

print("All feeds processed.")
summaries_text = "\n\n".join(feeds_summarIES)

# Save the intermediate summaries
with open(f"./output/summary_texts_feeds_{run_time}.txt", 'w') as f:
    f.write(summaries_text)

# summarize the final text
with open("./prompts/prompt_second_summary.md", 'r') as f:
    prompt_template_2 = f.read()

time.sleep(65)
prompt_final = prompt_template_2.format(summaries_text)
print("Calling LLM for final summary...")
answer_final = llm_call.call_llm(model, prompt_final)

# --- NEW: HTML Conversion, CSS Styling, and Saving ---
if answer_final:
    print("Final summary generated.")

    # 1. Convert Markdown to HTML body content
    html_body_content = markdown.markdown(answer_final)

    # 2. Define CSS for styling
    css_style = """
    body {
        direction: rtl;
        font-family: Arial, sans-serif;
        font-size: 20px; /* Increased font size for readability */
        line-height: 1.8;
        padding: 25px;
        background-color: #f8f9fa;
        color: #343a40;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #007bff;
        border-bottom: 2px solid #dee2e6;
        padding-bottom: 5px;
        margin-top: 30px;
    }
    ul {
        list-style-type: none; /* Remove default bullets */
        padding-right: 0;
        margin-right: 20px;
    }
    li {
        margin-bottom: 20px; /* Increase space between bullets */
        border-right: 4px solid #007bff; /* Custom bullet/marker on the right */
        padding-right: 15px;
    }
    strong {
        color: #dc3545; /* Highlight strong text */
    }
    """

    # 3. Assemble the full HTML document
    html_output = f"""
<!DOCTYPE html>
<html lang="he" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>סיכום חדשות - {run_time}</title>
    <style>
        {css_style}
    </style>
</head>
<body>
    {html_body_content}
</body>
</html>
"""

    # Print nicely to console
    print("\n--- FINAL SUMMARY (HTML Saved) ---")
    print(answer_final)
    print("----------------------------------\n")

    # Save to file with .html extension
    with open(f"./output/summary_text_{run_time}.html", 'w', encoding='utf-8') as f:
        f.write(html_output)
else:
    print("Final summary FAILED after all retries.")

print("Process complete.")