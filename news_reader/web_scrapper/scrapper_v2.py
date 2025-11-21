"""
This module provides functionality to scrape the full text of a news article from a given URL.
It uses playwright to control a headless browser and trafilatura to extract the main content from the HTML.
Stealth is used to avoid bot detection.
"""
import sys
import os

# Ensure the root directory is in the path for imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
# V2.0.0+ Import: Uses the Stealth class instead of stealth_sync function
from playwright_stealth import Stealth
import trafilatura


def get_full_article_text(url: str, print_every_step: bool = False) -> str:
    """
    Fetches the full text of a news article from a given URL.
    """
    # URL validation
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return "Error: Invalid URL provided."

    text_content = "Error: Could not fetch article text."

    try:
        # --- NEW: Correct Pattern for Playwright-Stealth v2.0.0 ---
        # We wrap the playwright context with Stealth().use_sync()
        # This automatically applies stealth to all pages created.
        stealth = Stealth()
        with stealth.use_sync(sync_playwright()) as p:

            # ARGS ARE CRITICAL FOR GITHUB ACTIONS (LINUX)
            # Without these flags, Chromium often hangs or crashes in the cloud container.
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            try:
                page = browser.new_page()

                # Note: In v2.0.0, stealth is applied automatically!
                # We do NOT need to call stealth_sync(page).

                # 1. Navigate
                if print_every_step:
                    print("Navigating to page...")

                # 15s timeout prevents one bad site from freezing the whole script
                page.goto(url, wait_until='domcontentloaded', timeout=15000)

                # 2. Cookie Banner (Hebrew)
                try:
                    button_selector = "text=אני מאשר/ת"
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
                # ALWAYS close the browser to prevent "zombie" processes
                browser.close()

    except Exception as e:
        return f"Error: An exception occurred during Playwright execution: {e}"

    return text_content