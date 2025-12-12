import os
import sys
import time
import warnings
import markdown
import toml as tomlib
from datetime import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from rss_reader import israel_rss_reader_v1 as israel_rss_reader
from custom_functions.custom_functions import count_tokens
from llm_call_functions import llm_call as llm_call
from web_scrapper import install_browsers
from email_sender import email_sender
# NEW: Import DB Manager
from news_db import db_manager

warnings.filterwarnings('ignore')


def run_process(parameters):
    # 1. Setup
    install_browsers.check_and_install_playwright_browsers()
    run_time = datetime.today().strftime('%Y-%m-%d')
    os.makedirs("./output", exist_ok=True)

    # Load Secrets
    with open("./.streamlit/secrets.toml", "r") as f:
        secret_data = tomlib.load(f)
    os.environ["GEMINI_API_KEY"] = secret_data["secrets"]["GEMINI_API_KEY"]
    os.environ["OPENAI_API_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]
    # Ensure DB keys are set for db_manager
    os.environ["SUPABASE_URL"] = secret_data["secrets"]["SUPABASE_URL"]
    os.environ["SUPABASE_KEY"] = secret_data["secrets"]["SUPABASE_KEY"]

    model = llm_call.get_model()

    # PART I: ACCUMULATION (Scrape & Summarize New) ---
    if parameters.scrap == 'yes':
        with open("./config/config.toml", "r") as f:
            config_data = tomlib.load(f)
        ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]

        # This will ONLY return articles we haven't seen yet (Thanks to DB check)
        full_text, count = israel_rss_reader.get_text_for_llm(ISRAELI_NEWS_FEEDS)

        if count > 0:
            print(f"Summarizing {count} new articles...")
            with open("./prompts/prompt_first_summary.md", 'r', encoding='utf-8') as f:
                prompt_template_1 = f.read()

            feed_texts = full_text.split("XXX")
            for i, text in enumerate(feed_texts):
                if not text.strip(): continue

                print(f"  - Summarizing Feed batch {i + 1}...")
                try:
                    prompt = prompt_template_1.format(text)
                    summary = llm_call.call_llm(model, prompt)

                    if summary:
                        # SAVE SUMMARY TO DB
                        db_manager.save_feed_summary(summary)
                        print("    > Saved summary to DB.")
                except Exception as e:
                    print(f"    [Error] Summarization failed: {e}")

                if i < len(feed_texts) - 1:
                    time.sleep(10)
        else:
            print("No new articles to process right now.")

    # PART II: REPORTING (Only if flag is set) ---
    if parameters.report == 'yes':
        print("Generating Final Daily Report...")

        # 1. Load ALL summaries from today (Morning + Afternoon + Evening)
        todays_summaries = db_manager.get_todays_summaries()

        if not todays_summaries:
            print("No summaries found in DB for today. Skipping email.")
            return

        combined_text = "\n\n".join(todays_summaries)
        print(f"Combining {len(todays_summaries)} summary blocks from DB.")

        # 2. Final Synthesis
        with open("./prompts/prompt_second_summary.md", 'r', encoding='utf-8') as f:
            prompt_template_2 = f.read()

        try:
            prompt_final = prompt_template_2.format(combined_text)
            answer_final = llm_call.call_llm(model, prompt_final)

            if answer_final:
                # HTML & Email
                answer_final = answer_final.replace("```markdown", "").replace("```", "").strip()
                from main_process import output_style
                html_body = markdown.markdown(answer_final)
                html_output = output_style.get_the_html(run_time, html_body)

                filename = f"./output/daily_report_{run_time}.html"
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(html_output)

                email_sender.send_summary_email(filename)
                print("Daily Email Sent Successfully.")
        except Exception as e:
            print(f"Final reporting failed: {e}")

    print("Workflow Complete.")