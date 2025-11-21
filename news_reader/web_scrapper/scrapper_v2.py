"""
This module provides functionality to scrape the full text of a news article from a given URL.
It uses playwright to control a headless browser and trafilatura to extract the main content from the HTML.
Stealth is used to avoid bot detection.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright
# We use the direct function call for stealth to avoid Context Manager issues in threads
from playwright_stealth import stealth_sync
import trafilatura


def get_full_article_text(url: str,
                          print_every_step: bool = False) -> str:
    """
    Fetches the full text of a news article from a given URL.
    """
    # URL validation
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return "Error: Invalid URL provided."

    text_content = "Error: Could not fetch article text."

    try:
        # We do NOT use the Stealth context manager wrapper here.
        # We manage the context manually to ensure we can close the browser in 'finally'.
        with sync_playwright() as p:
            # ARGS ARE CRITICAL FOR GITHUB ACTIONS (LINUX)
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            try:
                page = browser.new_page()

                # Apply stealth to this specific page
                stealth_sync(page)

                # 1. Navigate
                if print_every_step:
                    print("Navigating to page...")

                # Reduced timeout to 15s to prevent hanging threads
                page.goto(url, wait_until='domcontentloaded', timeout=15000)

                # 2. Cookie Banner (Hebrew)
                try:
                    button_selector = "text=אני מאשר/ת"
                    # Short timeout for button so we don't waste time
                    if page.query_selector(button_selector):
                        page.click(button_selector, timeout=1000)
                except Exception:
                    pass

                # 3. Scroll
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)

                # 4. Get HTML
                html_content = page.content()

                # 5. Extract
                text_content = trafilatura.extract(html_content)
                if not text_content:
                    return "Error: Trafilatura could not find main text."

            except Exception as e:
                if print_every_step:
                    print(f"Inner Scrape Error: {e}")
                return f"Error: {e}"

            finally:
                # THIS IS THE FIX: Always close the browser, no matter what.
                browser.close()

    except Exception as e:
        return f"Error: An exception occurred during Playwright execution: {e}"

    return text_content