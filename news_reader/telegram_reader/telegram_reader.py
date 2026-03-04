import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

STATE_FILE = "./config/telegram_state.json"

def get_last_datetime(channel_name):
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r") as f:
        try:
            data = json.load(f)
            if channel_name in data:
                return datetime.fromisoformat(data[channel_name])
        except Exception:
            pass
    return None

def save_last_datetime(channel_name, dt):
    data = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            try:
                data = json.load(f)
            except Exception:
                pass
    data[channel_name] = dt.isoformat()
    # ensure directory exists
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(data, f)


def fetch_telegram_messages(channel_name, last_date_time=None):
    base_url = f"https://t.me/s/{channel_name}"
    url = base_url
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko Chrome/91.0.4472.124 Safari/537.36)'
    }
    
    all_messages = []
    max_datetime_fetched = last_date_time
    
    # We loop backward through the pages
    while url:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"Failed to fetch {url}: HTTP {response.status_code}")
            break
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Each message is inside a div with class tgme_widget_message
        message_blocks = soup.find_all('div', class_='tgme_widget_message', attrs={'data-post': True})
        
        # message_blocks are in chronological order on the page, but we only really care about filtering by date
        page_messages = []
        reached_target_date = False
        
        for block in message_blocks:
            # Extract datetime
            time_element = block.find('time', class_='time')
            if not time_element or not time_element.has_attr('datetime'):
                continue
                
            msg_datetime_str = time_element['datetime']
            try:
                # Handle potential 'Z' suffix for UTC
                msg_datetime = datetime.fromisoformat(msg_datetime_str.replace('Z', '+00:00'))
            except ValueError:
                continue
                
            # Check if older than or equal to last_date_time
            if last_date_time and msg_datetime <= last_date_time:
                reached_target_date = True
                continue
                
            # Extract text
            text_element = block.find('div', class_='tgme_widget_message_text')
            if not text_element:
                continue
                
            text = text_element.get_text(separator=' ', strip=True)
            
            page_messages.append({
                'text': text,
                'datetime': msg_datetime,
            })
            
            if max_datetime_fetched is None or msg_datetime > max_datetime_fetched:
                max_datetime_fetched = msg_datetime

        # Append valid messages found on this page
        all_messages.extend(page_messages)
        
        # If any message on this page was older than the threshold, we can stop paginating backwards
        if reached_target_date:
            break
            
        # If no last_date_time was provided, we just fetch one page by default or limit the history depth
        if not last_date_time:
            break
            
        # Find the link to older posts
        older_link_element = soup.find('a', class_='tme_messages_more')
        if older_link_element and older_link_element.has_attr('href'):
            # The older link is like /s/channel_name?before=1234
            url = f"https://t.me{older_link_element['href']}"
        else:
            # Reached the very beginning of the channel
            url = None

    # Sort all_messages chronologically 
    all_messages.sort(key=lambda x: x['datetime'])
            
    return all_messages, max_datetime_fetched

def format_messages_for_llm(messages):
    formatted = []
    for msg in messages:
        # standardizing display output to have clear datetime format
        dt_str = msg['datetime'].strftime('%Y-%m-%d %H:%M:%S')
        formatted.append(f"{dt_str}: {msg['text']} |||")
    return "\n".join(formatted)

if __name__ == "__main__":
    from datetime import timezone, timedelta
    
    # Test block for Phase 1 testing
    channels = ["yediotnews25", "abualiexpress"]
    test_last_date = datetime.now(timezone.utc) - timedelta(hours=5)
    print(f"Fetching messages newer than: {test_last_date}")
    
    all_formatted_msgs = []
    
    for channel in channels:
        print(f"\n--- Fetching from {channel} ---")
        msgs, latest_dt = fetch_telegram_messages(channel, test_last_date)
        print(f"Found {len(msgs)} messages.")
        if msgs:
            formatted = format_messages_for_llm(msgs)
            all_formatted_msgs.append(formatted)
            print("Sample formatted output (last 2 messages):")
            print(format_messages_for_llm(msgs[-2:]))
            print(f"Latest datetime fetched: {latest_dt}")
        print("-" * 50)
        
    # Save the actual full text dump for prompt testing
    with open("test_telegram_output.txt", "w", encoding="utf-8") as f:
        f.write("\n\n".join(all_formatted_msgs))
