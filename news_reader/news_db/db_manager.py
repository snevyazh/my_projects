import os
import toml as tomlib
from supabase import create_client, Client
from datetime import datetime
import pytz


def get_db_client():
    # Try loading from secrets file first (Local dev)
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    # If not in env, try secrets.toml
    if not url:
        try:
            with open(".streamlit/secrets.toml", "r") as f:
                secrets = tomlib.load(f)
                url = secrets["secrets"]["SUPABASE_URL"]
                key = secrets["secrets"]["SUPABASE_KEY"]
        except Exception:
            pass

    if not url or not key:
        print("[DB Error] Missing Supabase URL or Key.")
        return None

    return create_client(url, key)


def is_article_processed(url):
    """Checks if a URL is already in the database."""
    supabase = get_db_client()
    if not supabase: return False

    try:
        response = supabase.table("processed_articles").select("url").eq("url", url).execute()
        # If we get data back, it means it exists
        return len(response.data) > 0
    except Exception as e:
        print(f"[DB Error] Check failed: {e}")
        return False


def mark_article_processed(url, title=""):
    """Saves a URL to the database so we don't scrape it again."""
    supabase = get_db_client()
    if not supabase: return

    try:
        data = {"url": url, "title": title}
        supabase.table("processed_articles").insert(data).execute()
    except Exception as e:
        # Ignore duplicate key errors if race condition
        print(f"[DB Log] Could not save {url}: {e}")


def delete_old_articles(days_to_keep=7):
    """Deletes old processed article logs and daily summaries to keep the DB small."""
    supabase = get_db_client()
    if not supabase: return
    
    try:
        from datetime import timedelta
        threshold_date = datetime.now(pytz.utc) - timedelta(days=days_to_keep)
        threshold_iso = threshold_date.isoformat()
        
        # 1. Clean processed_articles (using standard Supabase 'created_at')
        response_articles = supabase.table("processed_articles").delete().lt("created_at", threshold_iso).execute()
        deleted_articles = len(response_articles.data) if response_articles.data else 0
        if deleted_articles > 0:
            print(f"[DB Cleanup] Deleted {deleted_articles} old tracking URLs.")
            
        # 2. Clean daily_summaries (using our custom 'run_date' string YYYY-MM-DD format)
        threshold_run_date = threshold_date.strftime("%Y-%m-%d")
        response_summaries = supabase.table("daily_summaries").delete().lt("run_date", threshold_run_date).execute()
        deleted_summaries = len(response_summaries.data) if response_summaries.data else 0
        if deleted_summaries > 0:
            print(f"[DB Cleanup] Deleted {deleted_summaries} old intermediate summaries.")
            
    except Exception as e:
        print(f"[DB Cleanup Error] Failed to complete database cleanup: {e}")


def save_feed_summary(summary_text):
    """Saves a chunk of AI summary to the database."""
    supabase = get_db_client()
    if not supabase: return

    try:
        # Get today's date in proper format
        today = datetime.now().strftime("%Y-%m-%d")
        data = {
            "run_date": today,
            "summary_text": summary_text
        }
        supabase.table("daily_summaries").insert(data).execute()
        print("[DB Success] Saved intermediate summary to DB.")
    except Exception as e:
        print(f"[DB Error] Failed to save summary: {e}")


def get_todays_summaries():
    """Retrieves all summaries generated today."""
    supabase = get_db_client()
    if not supabase: return []

    try:
        today = datetime.now().strftime("%Y-%m-%d")
        response = supabase.table("daily_summaries").select("summary_text").eq("run_date", today).execute()

        # Extract the text list
        summaries = [item['summary_text'] for item in response.data]
        return summaries
    except Exception as e:
        print(f"[DB Error] Failed to retrieve summaries: {e}")
        return []