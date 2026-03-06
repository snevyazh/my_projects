import os
import time
import toml as tomlib
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from llm_call_functions import llm_call_open_ai as llm_call
from news_db import db_manager
from telegram_reader import telegram_reader
from telegram_reader import telegram_sender


def run_telegram_update():
    print(f"[{datetime.now()}] Starting Incremental Telegram Update...")
    
    with open("./.streamlit/secrets.toml", "r") as f:
        secret_data = tomlib.load(f)
        
    os.environ["OPEN_AI_KEY"] = secret_data["secrets"]["OPEN_AI_KEY"]
    os.environ["SUPABASE_URL"] = secret_data["secrets"]["SUPABASE_URL"]
    os.environ["SUPABASE_KEY"] = secret_data["secrets"]["SUPABASE_KEY"]

    with open("./config/config.toml", "r") as f:
        config_data = tomlib.load(f)

    telegram_channels = config_data.get("telegram", {}).get("channels", [])
    model = config_data.get("telegram", {}).get("model", "gpt-5-nano")
    
    if not telegram_channels:
        print("No Telegram channels configured. Exiting.")
        return

    # Load prompt
    try:
        with open("./prompts/prompt_telegram_summary.md", 'r', encoding='utf-8') as f:
            prompt_telegram = f.read()
    except FileNotFoundError:
        print("[Error] prompt_telegram_summary.md not found.")
        return

    all_combined_msgs = []
    latest_datetimes = {}

    # 1. Fetch from all channels independently using their own state
    for channel in telegram_channels:
        print(f"Fetching Telegram channel: {channel}")
        last_dt = db_manager.get_telegram_state(channel)
        
        if last_dt:
            print(f"  > Last processed datetime from DB: {last_dt}")
        else:
            print(f"  > No previous state found for {channel}. Will only fetch latest block.")
            
        msgs, new_latest_dt = telegram_reader.fetch_telegram_messages(channel, last_dt)
        
        if not msgs:
            print(f"  > No new messages for {channel}")
            continue
            
        print(f"  > Found {len(msgs)} new messages.")
        
        # Store for the combined list
        all_combined_msgs.extend(msgs)
        latest_datetimes[channel] = new_latest_dt
        time.sleep(1)

    if not all_combined_msgs:
        print("No new updates from any channel. Exiting.")
        return

    # 2. Sort all combined messages chronologically before sending to LLM
    all_combined_msgs.sort(key=lambda x: x['datetime'])
    formatted_msgs = telegram_reader.format_messages_for_llm(all_combined_msgs)

    # 3. Summarize with LLM
    print(f"Summarizing {len(all_combined_msgs)} total granular updates using {model}...")
    prompt = prompt_telegram.format(formatted_msgs)
    
    try:
        summary_markdown = llm_call.call_llm(model, prompt)
        
        if not summary_markdown:
            print("[Error] LLM returned empty summary.")
            return

        print("  > LLM Summary generated. Formatting for Telegram...")
        
        # 4. Format for Telegram and Send
        telegram_html = telegram_sender.format_markdown_for_telegram(summary_markdown)
        success = telegram_sender.send_telegram_message(telegram_html)
        
        # 5. Only save state if send was actually successful!
        if success:
            for channel, new_dt in latest_datetimes.items():
                if new_dt:
                    db_manager.save_telegram_state(channel, new_dt)
            print("Incremental update complete.")
        else:
            print("[CRITICAL] Failed to send Telegram message. State was NOT updated to prevent data loss.")

    except Exception as e:
        print(f"[CRITICAL ERROR] Telegram incremental failed: {e}")

if __name__ == "__main__":
    run_telegram_update()
