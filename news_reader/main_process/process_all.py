import os
import sys
import time
from main_process import find_file, output_style
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
from email_sender import email_sender

def run_process(parameters):
    # 1. check and install playwright
    install_browsers.check_and_install_playwright_browsers()

    # 2. parse args from main
    full_text_for_llm = ""
    run_time = datetime.today().strftime('%Y-%m-%d')

    if parameters.scrap == 'yes':
        # run scrapping
        # real-time Hebrew news feeds
        with open("./config/config.toml", "r") as f:
            config_data = tomlib.load(f)
        ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]
        workers = config_data["process"]["workers"]

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
    elif  parameters.scrap == 'no' and parameters.date:
        run_time_manual = parameters.date
        # run_time = datetime.today().strftime('%Y-%m-%d')
        search_directory = "./output/"
        filename_to_open = "full_text_{run_time_manual}.txt"
        if find_file.find_file_exists(search_directory, filename_to_open):
            input_file_path = f"{search_directory}{filename_to_open}"
            with open(input_file_path, 'r') as f:
                full_text_for_llm = f.read()
        else:
            filename_with_max_date = find_file.find_file_with_full_text(search_directory)
            if filename_with_max_date:
                with open(filename_with_max_date, 'r') as f:
                    full_text_for_llm = f.read()
            else:
                print("No file exusts to satisfy the conversion without scrapping")
                sys.exit()

    else:
        print("dead end")
    # set the env
    with open("./.streamlit/secrets.toml", "r") as f:
            secret_data = tomlib.load(f)
    os.environ["GEMINI_API_KEY"] = secret_data["secrets"]["GEMINI_API_KEY"]
    os.environ["OPENAI_API_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]
    # run LLM
    text_by_stream = full_text_for_llm.split("XXX")

    with open("./prompts/prompt_first_summary.md", 'r') as f:
        prompt_template_1 = f.read()

    feeds_summaries = []

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
            feeds_summaries.append(answer_for_feed)
        else:
            print(f"    - Feed {i + 1} FAILED to summarize after retries.")

        # Add a delay to avoid hitting rate limits, but not on the last item
        if i < len(text_by_stream) - 1:
            print("Waiting for 65 seconds before the next call...")
            time.sleep(65)

    print("All feeds processed.")
    summaries_text = "\n\n".join(feeds_summaries)

    # Save the intermediate summaries
    with open(f"./output/summary_texts_feeds_{run_time}.txt", 'w') as f:
        f.write(summaries_text)

    # summarize the final text
    with open("./prompts/prompt_second_summary.md", 'r') as f:
        prompt_template_2 = f.read()

    time.sleep(80)
    prompt_final = prompt_template_2.format(summaries_text)
    print("Calling LLM for final summary...")
    answer_final = llm_call.call_llm(model, prompt_final)

    # --- NEW: HTML Conversion, CSS Styling, and Saving ---
    if answer_final:
        print("Final summary generated.")
        answer_final = answer_final.replace("```markdown", "").replace("```", "").strip()
        # 1. Convert Markdown to HTML body content
        html_body_content = markdown.markdown(answer_final)

        # 2. Define CSS for styling
        html_output = output_style.get_the_html(run_time, html_body_content)
        # Save to file with .html extension
        final_html_filename = f"./output/summary_text_{run_time}.html"
        with open(final_html_filename, 'w', encoding='utf-8') as f:
            f.write(html_output)

        print("Sending email...")
        email_sender.send_summary_email(final_html_filename)
    else:
        print("Final summary FAILED after all retries.")

    print("Process complete.")
