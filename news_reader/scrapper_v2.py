"""
This module provides functionality to scrape the full text of a news article from a given URL.
It uses playwright to control a headless browser and trafilatura to extract the main content from the HTML.
Stealth is used to avoid bot detection.
"""
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
import trafilatura


def get_full_article_text(url: str,
                          print_every_step: bool = False) -> str:
    """
    Fetches the full text of a news article from a given URL.

    This function uses a stealth-patched headless browser (Chromium) to navigate to the
    provided URL, handle potential cookie banners, scroll to load lazy-loaded content,
    and then extracts the main article text using trafilatura.

    Args:
        url: The URL of the news article to scrape.
        print_every_step: if the function needs to print to stdout every step of scrapping, False is the default.

    Returns:
        The extracted full text of the article as a string.
        If any step fails, it returns an error message.

    """
    # URL validation
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return "Error: Invalid URL provided."

    text_content = "Error: Could not fetch article text."

    try:
        # Using Stealth to appear more like a regular user
        with Stealth().use_sync(sync_playwright()) as p:
            # Launch a headless Chromium browser
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            # 1. Navigate to the target page
            if print_every_step:
                print("Navigating to page (with stealth)...")
            page.goto(url, wait_until='domcontentloaded', timeout=20000)

            # 2. Attempt to dismiss a common cookie consent banner.
            # This is specific to a certain site layout and might need adjustment for others.
            try:
                # Selector for a common cookie banner button text in Hebrew
                button_selector = "text=אני מאשר/ת"
                page.wait_for_selector(button_selector, timeout=3000)
                page.click(button_selector)
                if print_every_step:
                    print("Clicked cookie banner.")
                # Wait  for the banner to disappear and the page to settle
                page.wait_for_timeout(1000)
            except Exception:
                # If the banner is not found, just continue.
                if print_every_step:
                    print("Cookie banner not found or could not be clicked.")
                pass

            # 3. Scroll down the page to trigger any lazy-loaded content.
            if print_every_step:
                print("Scrolling down to trigger lazy-loading...")
            page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
            # Wait for the new content to potentially load
            page.wait_for_timeout(2000)

            # 4. Get the fully rendered HTML content of the page.
            if print_every_step:
                print("Getting rendered HTML...")
            html_content = page.content()

            # Close the browser instance to free up resources
            browser.close()

            # 5. Use trafilatura to extract the main article text from the HTML.
            if print_every_step:
                print("Extracting text with Trafilatura...")
            text_content = trafilatura.extract(html_content)

            # Check if trafilatura was able to extract any content.
            if not text_content:
                return "Error: Trafilatura could not find main text."

    except Exception as e:
        # Catch any exceptions during the playwright or trafilatura process
        if print_every_step:
            print(f"Failed to scrape {url}. Error: {e}")
        return f"Error: An exception occurred while scraping the article {url}: {e}"

    return text_content
