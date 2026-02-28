"""
This module provides functionality to scrape the full text of a news article from a given URL.
It uses playwright to control a headless browser and BeautifulSoup to extract the main content.
Stealth is used to avoid bot detection.
"""
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from bs4 import BeautifulSoup
import trafilatura


def get_full_article_text(url: str, print_every_step: bool = False) -> str:
    """
    Fetches the full text of a news article from a given URL using BeautifulSoup
    for known sites, gracefully falling back to trafilatura.
    """
    # URL validation
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return "Error: Invalid URL provided."

    text_content = "Error: Could not fetch article text."

    try:
        stealth = Stealth()
        with stealth.use_sync(sync_playwright()) as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )

            try:
                page = browser.new_page()

                if print_every_step:
                    print(f"Navigating to {url}...")

                page.goto(url, wait_until='domcontentloaded', timeout=15000)

                # Cookie Banner (Hebrew)
                try:
                    button_selector = "text=אני מאשר/ת"
                    if page.query_selector(button_selector):
                        page.click(button_selector, timeout=1000)
                except Exception:
                    pass

                # Scroll
                page.evaluate("window.scrollBy(0, document.body.scrollHeight)")
                page.wait_for_timeout(1000)

                html_content = page.content()

                # Extract using BeautifulSoup
                soup = BeautifulSoup(html_content, 'html.parser')
                extracted_text = ""
                
                if "ynet.co.il" in url:
                    article_body = soup.find('div', class_='text_editor_class') or \
                                   soup.select_one('[data-testera="article-body"]') or \
                                   soup.select_one('.ArticleText') or \
                                   soup.select_one('.article-body')
                    if article_body:
                        blocks = article_body.find_all(['p', 'div', 'span'], dir="rtl")
                        if not blocks:
                            blocks = article_body.find_all('p')
                        extracted_list = []
                        for b in blocks:
                            t = b.get_text(strip=True)
                            if t and len(t) > 20 and t not in extracted_list:
                                extracted_list.append(t)
                        extracted_text = "\n".join(extracted_list)
                        
                elif "walla.co.il" in url:
                    article_body = soup.find('section', class_='article-content') or \
                                   soup.find('article') or \
                                   soup.select_one('.multi-article-content') or \
                                   soup.select_one('.item-main-content')
                    if article_body:
                        paragraphs = article_body.find_all('p')
                        extracted_list = [p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)]
                        extracted_text = "\n".join(extracted_list)
                
                # Fallback to Trafilatura if custom BS4 logic missed it or it's a different site
                if not extracted_text or len(extracted_text) < 100:
                    if print_every_step:
                        print("Falling back to Trafilatura extraction...")
                    extracted_text = trafilatura.extract(html_content) or ""
                
                if extracted_text:
                    text_content = extracted_text
                else:
                    text_content = "Error: Could not find main text."

            except Exception as e:
                if print_every_step:
                    print(f"Inner Scrape Error: {e}")
                return f"Error: {e}"

            finally:
                browser.close()

    except Exception as e:
        return f"Error: An exception occurred during Playwright execution: {e}"

    text_content = f"URL: {url}\n{text_content}\n\n"
    return text_content
