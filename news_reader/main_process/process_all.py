import os
import sys
import time
import warnings
import markdown
import toml as tomlib
from datetime import datetime

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from rss_reader import israel_rss_reader_v1 as israel_rss_reader
from llm_call_functions import llm_call_open_ai as llm_call
from web_scrapper import install_browsers
from email_sender import email_sender
from news_db import db_manager

warnings.filterwarnings('ignore')


def run_process(parameters):
    install_browsers.check_and_install_playwright_browsers()
    run_time = datetime.today().strftime('%Y-%m-%d')
    os.makedirs("./output", exist_ok=True)

    with open("./.streamlit/secrets.toml", "r") as f:
        secret_data = tomlib.load(f)
    os.environ["OPEN_AI_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]
    os.environ["SUPABASE_URL"] = secret_data["secrets"]["SUPABASE_URL"]
    os.environ["SUPABASE_KEY"] = secret_data["secrets"]["SUPABASE_KEY"]

    model = llm_call.get_model()

    # --- PART A: ACCUMULATION ---
    if parameters.scrap == 'yes':
        with open("./config/config.toml", "r") as f:
            config_data = tomlib.load(f)
        ISRAELI_NEWS_FEEDS = config_data["feeds"]["ISRAELI_NEWS_FEEDS"]

        # Get structured dictionary instead of string
        feed_data_dict, count = israel_rss_reader.get_text_for_llm(ISRAELI_NEWS_FEEDS)

        if count > 0:
            print(f"Summarizing {count} new articles...")
            with open("./prompts/prompt_first_summary.md", 'r', encoding='utf-8') as f:
                prompt_template_1 = f.read()

            # Iterate through the feeds in the dictionary
            for feed_url, data in feed_data_dict.items():
                texts = data['texts']
                metadata_list = data['metadata']  # List of (url, title) tuples

                if not texts:
                    continue

                # Combine all articles for this feed into one prompt
                combined_text = "\n\n".join(texts)

                print(f"  - Summarizing batch for feed...")
                try:
                    prompt = prompt_template_1.format(combined_text)
                    summary = llm_call.call_llm(model, prompt)

                    if summary:
                        # 1. SAVE SUMMARY
                        db_manager.save_feed_summary(summary)
                        print("    > Summary saved.")

                        # 2. COMMIT URLs (Transactional Safety)
                        # We only mark them as processed NOW, after success.
                        for link, title in metadata_list:
                            db_manager.mark_article_processed(link, title)
                        print(f"    > Marked {len(metadata_list)} articles as processed.")

                except Exception as e:
                    print(f"    [CRITICAL ERROR] Feed failed: {e}")
                    print("    > Articles were NOT marked as processed and will be retried next time.")

                time.sleep(2)
        else:
            print("No new articles to process.")

    # --- PART B: REPORTING ---
    if parameters.report == 'yes':
        print("Generating Final Daily Report...")
        todays_summaries = db_manager.get_todays_summaries()

        if not todays_summaries:
            print("No summaries found in DB for today. Skipping email.")
            return

        combined_text = "\n\n".join(todays_summaries)
        print(f"Combining {len(todays_summaries)} summary blocks.")

        with open("./prompts/prompt_second_summary.md", 'r', encoding='utf-8') as f:
            prompt_template_2 = f.read()

        try:
            prompt_final = prompt_template_2.format(combined_text)
            answer_final = llm_call.call_llm(model, prompt_final)

            if answer_final:
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