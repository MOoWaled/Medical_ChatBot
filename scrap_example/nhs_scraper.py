"""
NHS Inform Scraper - CSV Export version
Scrapes illnesses and conditions from NHS Inform A-Z index, extracts symptoms, causes, warnings, and recommendations, and saves the data to a CSV file.
Designed in the style of the scrap_example notebook.
"""

import time
import re
import logging
from urllib.parse import urljoin
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd

# Set up clean logging output
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

BASE_URL = "https://www.nhsinform.scot"
INDEX_URL = "https://www.nhsinform.scot/illnesses-and-conditions/a-to-z/"
OUTPUT_CSV = "nhs_conditions.csv"

# Browser-like headers to identify our scraper politely
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive"
}

# Reusable cloudscraper session (bypasses Cloudflare-style protection/403 blocks)
_scraper = cloudscraper.create_scraper(
    browser={
        "browser": "chrome",
        "platform": "windows",
        "desktop": True,
    }
)
_scraper.headers.update(HEADERS)


def fetch_html(url: str) -> BeautifulSoup | None:
    """
    Fetch HTML content from a URL and return a BeautifulSoup object.
    Retries up to 3 times with exponential backoff on failure.
    """
    for attempt in range(1, 4):
        try:
            resp = _scraper.get(url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "lxml")
            else:
                logger.warning(f"[{attempt}/3] {url} -> HTTP status {resp.status_code}")
        except Exception as e:
            logger.warning(f"[{attempt}/3] Request failed for {url}: {e}")
        
        if attempt < 3:
            time.sleep(attempt * 3)
            
    logger.error(f"Failed to fetch content after 3 attempts: {url}")
    return None


def clean_text(text: str) -> str:
    """
    Clean extracted text: remove feedback confirmation text, share buttons,
    social media widgets, and collapse multiple whitespaces.
    """
    if not text:
        return ""
    
    # Clean NHS Inform specific widget and feedback text
    junk_patterns = [
        r"Thank\s+You\s+Your\s+feedback\s+has\s+been\s+received",
        r"Was\s+this\s+page\s+helpful\??",
        r"Share\s+this\s+page",
        r"Last\s+updated:?\s*\d{1,2}\s+\w+\s+\d{4}",
        r"Source:?\s*NHS\s+inform",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Collapse all whitespace and strip edges
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_index_page(soup: BeautifulSoup) -> list[dict]:
    """
    Parses the A-Z index page and returns a list of dictionaries with condition name and URL.
    """
    conditions = []
    seen_urls = set()
    
    all_links = soup.find_all("a", href=True)
    for link in all_links:
        href = link["href"]
        name = link.get_text(strip=True)
        
        if not name or len(name) < 2:
            continue
            
        full_url = urljoin(BASE_URL, href)
        
        # Only parse actual conditions under illnesses-and-conditions
        if "/illnesses-and-conditions/" not in full_url:
            continue
        if full_url.rstrip("/") == INDEX_URL.rstrip("/"):
            continue
        if href.startswith("#"):
            continue
        if full_url.rstrip("/").endswith("/a-to-z"):
            continue
            
        # Ensure it's not a top-level category page
        path = full_url.replace(BASE_URL, "").strip("/")
        path_segments = [s for s in path.split("/") if s]
        if len(path_segments) < 3:
            continue
            
        normalized_url = full_url.rstrip("/")
        if normalized_url in seen_urls:
            continue
        
        seen_urls.add(normalized_url)
        conditions.append({
            "name": name,
            "url": full_url
        })
        
    return conditions


def _collect_section_content(heading_tag) -> str:
    """
    Collects paragraph, list, and container text between heading_tag and the next heading.
    """
    heading_level = int(heading_tag.name[1])
    content_parts = []
    
    for sibling in heading_tag.find_next_siblings():
        # Stop at the next heading of same or higher hierarchy
        if sibling.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            sibling_level = int(sibling.name[1])
            if sibling_level <= heading_level:
                break
                
        # Extract text from tag components
        if sibling.name in ("p", "ul", "ol", "dl", "blockquote", "table"):
            text = clean_text(sibling.get_text())
            if text:
                content_parts.append(text)
        elif sibling.name == "div":
            # Search within nested elements in divs
            for child in sibling.find_all(["p", "ul", "ol", "li", "dl", "blockquote"], recursive=True):
                text = clean_text(child.get_text())
                if text:
                    content_parts.append(text)
                    
    return "\n".join(content_parts) if content_parts else ""


def _extract_care_cards(soup: BeautifulSoup) -> str:
    """
    Extract warning/alert content from special callouts, panels, or care cards.
    """
    warning_parts = []
    selectors = [
        "[class*='care-card']",
        "[class*='callout']",
        "[class*='urgent']",
        "[class*='warning']",
        "[class*='alert']",
        "[class*='important']",
    ]
    for selector in selectors:
        for el in soup.select(selector):
            text = clean_text(el.get_text())
            if text and len(text) > 20:
                warning_parts.append(text)
                
    return "\n".join(warning_parts) if warning_parts else ""


def parse_condition_page(soup: BeautifulSoup, name: str, url: str) -> dict:
    """
    Parses a condition page and returns a structured dictionary of its sections.
    """
    # Pre-cleanup: remove boilerplate and navigation before content extraction
    noise_selectors = [
        "[class*='feedback']", "[class*='rating']", "[class*='share']",
        "[id*='feedback']", "nav", "header", "footer",
        "[class*='breadcrumb']", "[class*='cookie']", "[class*='banner']"
    ]
    for selector in noise_selectors:
        for el in soup.select(selector):
            el.decompose()

    h1 = soup.find("h1")
    title = clean_text(h1.get_text()) if h1 else name

    # Extract overview paragraph (text before the first heading)
    overview_parts = []
    if h1:
        for sibling in h1.find_next_siblings():
            if sibling.name and sibling.name.startswith("h"):
                break
            if sibling.name in ("p", "ul", "ol"):
                text = clean_text(sibling.get_text())
                if text:
                    overview_parts.append(text)
    overview = "\n".join(overview_parts)

    s_patterns = ["symptoms", "signs and symptoms", "symptom"]
    c_patterns = ["causes", "cause", "what causes", "risk factors"]
    w_patterns = ["when to get help", "when to see a gp", "urgent advice", "warning signs", "complications"]
    r_patterns = ["treatment", "treatments", "self-help", "living with", "managing", "prevention"]

    symptoms, causes, warnings, recommendations = "", "", "", ""

    # Parse headings to group sections
    for heading in soup.find_all(["h2", "h3"]):
        heading_text = heading.get_text().lower().strip()
        section_content = _collect_section_content(heading)
        if not section_content:
            continue
            
        if any(p in heading_text for p in s_patterns):
            symptoms = (symptoms + "\n" + section_content).strip() if symptoms else section_content
        elif any(p in heading_text for p in c_patterns):
            causes = (causes + "\n" + section_content).strip() if causes else section_content
        elif any(p in heading_text for p in w_patterns):
            warnings = (warnings + "\n" + section_content).strip() if warnings else section_content
        elif any(p in heading_text for p in r_patterns):
            recommendations = (recommendations + "\n" + section_content).strip() if recommendations else section_content

    # Append warning info from care-cards
    care_card_text = _extract_care_cards(soup)
    if care_card_text and care_card_text not in warnings:
        warnings = (warnings + "\n" + care_card_text).strip() if warnings else care_card_text

    # Fallback: some pages describe symptoms in the intro paragraph instead of
    # under a dedicated "Symptoms" heading (e.g. "About X" style pages).
    # Rather than losing that text, use it to fill the gap.
    if not symptoms and overview:
        symptoms = overview

    return {
        "condition": title,
        "source_url": url,
        "symptoms": symptoms or None,
        "causes": causes or None,
        "warnings": warnings or None,
        "recommendations": recommendations or None
    }


def main():
    logger.info("Checking robots.txt on NHS Inform...")
    robots_soup = fetch_html(f"{BASE_URL}/robots.txt")
    if robots_soup:
        logger.info("robots.txt content successfully fetched.")
        
    logger.info(f"Fetching A-Z conditions index from {INDEX_URL}...")
    index_soup = fetch_html(INDEX_URL)
    if not index_soup:
        logger.error("Failed to parse A-Z index page.")
        return
        
    conditions = parse_index_page(index_soup)
    logger.info(f"Found {len(conditions)} conditions to scrape.")
    
    scraped_data = []
    total_conditions = len(conditions)
    logger.info(f"Scraping all {total_conditions} conditions...")
    
    for i, condition in enumerate(conditions, 1):
        name = condition["name"]
        url = condition["url"]
        
        logger.info(f"[{i}/{total_conditions}] Scraping: {name} ...")
        cond_soup = fetch_html(url)
        if cond_soup:
            data = parse_condition_page(cond_soup, name, url)
            scraped_data.append(data)
            logger.info(f"  Successfully extracted {name}")
        else:
            logger.error(f"  Failed to scrape {name}")
            
        # Save progress every 10 conditions
        if i % 10 == 0:
            df = pd.DataFrame(scraped_data)
            try:
                df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
                logger.info(f"  [Progress] Saved {len(scraped_data)} records to '{OUTPUT_CSV}'.")
            except PermissionError:
                alternative_output = "nhs_conditions_scraped.csv"
                df.to_csv(alternative_output, index=False, encoding="utf-8-sig")
                logger.info(f"  [Progress] Saved {len(scraped_data)} records to '{alternative_output}'.")
            
        # Respectful delay between hits
        time.sleep(1.5)
        
    # Create DataFrame and export to CSV
    df = pd.DataFrame(scraped_data)
    try:
        df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
        logger.info(f"Successfully saved {len(scraped_data)} records to '{OUTPUT_CSV}'.")
    except PermissionError:
        alternative_output = "nhs_conditions_scraped.csv"
        df.to_csv(alternative_output, index=False, encoding="utf-8-sig")
        logger.warning(f"Could not write to '{OUTPUT_CSV}' because the file is open or locked. "
                       f"Saved {len(scraped_data)} records to '{alternative_output}' instead.")


if __name__ == "__main__":
    main()