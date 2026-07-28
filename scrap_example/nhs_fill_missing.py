"""
NHS Inform Scraper - "Fill Missing Values" version
=====================================================
Builds on nhs_scraper.py but fixes the two root causes of the None values
found in nhs_conditions.csv:

  1. PARSING GAPS: the original heading-pattern lists were too narrow
     (e.g. "Signs of X" was not matched because it doesn't contain the
     literal word "symptom"; "diagnosis", "self-care", "medicines" etc.
     were not recognised either). This version uses a much broader
     synonym list.

  2. HUB / CATEGORY PAGES: some A-Z entries (e.g. "Autism", "Heart
     disease", "Liver disease", "Inflammatory bowel disease (IBD)") are
     landing pages that just link out to several child condition pages
     rather than containing their own Symptoms/Causes sections. This
     version detects thin pages and follows their internal
     sub-condition links, concatenating the children's content, and
     flags the row with is_hub_page=True so you can decide whether to
     keep, merge, or drop it before modelling.

IMPORTANT: This script needs real internet access + cloudscraper to get
past NHS Inform's bot detection (confirmed while diagnosing this data:
a plain fetch gets blocked, cloudscraper does not). Run it on Kaggle or
your local machine - it will NOT work in a sandboxed/offline environment.

Usage:
    python nhs_fill_missing.py --input nhs_conditions.csv --output nhs_conditions_filled.csv
"""

import argparse
import time
import re
import logging
from urllib.parse import urljoin, urlparse
import cloudscraper
from bs4 import BeautifulSoup
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

BASE_URL = "https://www.nhsinform.scot"
INDEX_URL = "https://www.nhsinform.scot/illnesses-and-conditions/a-to-z/"

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Connection": "keep-alive",
}

_scraper = cloudscraper.create_scraper(browser={"browser": "chrome", "platform": "windows", "desktop": True})
_scraper.headers.update(HEADERS)

# --- broadened heading synonym lists -------------------------------------------------
S_PATTERNS = ["symptom", "signs of", "signs and", "how do i know", "how you"]
C_PATTERNS = ["cause", "risk factor", "why does", "what causes", "who is affected"]
W_PATTERNS = ["when to get help", "when to see", "urgent advice", "warning sign",
              "complication", "emergency", "get help", "red flag", "seek help", "diagnosis", "diagnosing"]
R_PATTERNS = ["treatment", "self-help", "self-care", "self care", "living with", "managing",
              "prevention", "medicine", "medication", "how to treat", "outlook", "support"]


def fetch_html(url: str):
    for attempt in range(1, 4):
        try:
            resp = _scraper.get(url, timeout=20)
            if resp.status_code == 200:
                return BeautifulSoup(resp.text, "lxml")
            logger.warning(f"[{attempt}/3] {url} -> HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[{attempt}/3] Request failed for {url}: {e}")
        if attempt < 3:
            time.sleep(attempt * 3)
    logger.error(f"Failed to fetch after 3 attempts: {url}")
    return None


def clean_text(text: str) -> str:
    if not text:
        return ""
    junk_patterns = [
        r"Thank\s+You\s+Your\s+feedback\s+has\s+been\s+received",
        r"Was\s+this\s+page\s+helpful\??",
        r"Share\s+this\s+page",
        r"Last\s+updated:?\s*\d{1,2}\s+\w+\s+\d{4}",
        r"Source:?\s*NHS\s+inform",
    ]
    for pattern in junk_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def build_index_map() -> dict:
    """Re-crawl the A-Z index and return {condition_name: url}."""
    soup = fetch_html(INDEX_URL)
    mapping = {}
    if not soup:
        return mapping
    for link in soup.find_all("a", href=True):
        href = link["href"]
        name = link.get_text(strip=True)
        if not name or len(name) < 2 or href.startswith("#"):
            continue
        full_url = urljoin(BASE_URL, href)
        if "/illnesses-and-conditions/" not in full_url:
            continue
        path_segments = [s for s in full_url.replace(BASE_URL, "").strip("/").split("/") if s]
        if len(path_segments) < 3 or path_segments[-1] == "a-to-z":
            continue
        mapping[name] = full_url.rstrip("/") + "/"
    logger.info(f"Index re-crawl found {len(mapping)} name->url mappings.")
    return mapping


def _collect_section_content(heading_tag) -> str:
    heading_level = int(heading_tag.name[1])
    parts = []
    for sibling in heading_tag.find_next_siblings():
        if sibling.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if int(sibling.name[1]) <= heading_level:
                break
        if sibling.name in ("p", "ul", "ol", "dl", "blockquote", "table"):
            text = clean_text(sibling.get_text())
            if text:
                parts.append(text)
        elif sibling.name == "div":
            for child in sibling.find_all(["p", "ul", "ol", "li", "dl", "blockquote"], recursive=True):
                text = clean_text(child.get_text())
                if text:
                    parts.append(text)
    return "\n".join(parts)


def _extract_care_cards(soup: BeautifulSoup) -> str:
    parts = []
    for selector in ["[class*='care-card']", "[class*='callout']", "[class*='urgent']",
                      "[class*='warning']", "[class*='alert']", "[class*='important']"]:
        for el in soup.select(selector):
            text = clean_text(el.get_text())
            if text and len(text) > 20:
                parts.append(text)
    return "\n".join(parts)


def _find_child_condition_links(soup: BeautifulSoup, page_url: str) -> list:
    """For hub/category pages: find links to sibling/child condition pages
    (same URL prefix, one level deeper) so we can pull their content in."""
    prefix = page_url.rstrip("/")
    children = []
    seen = set()
    main = soup.find("main") or soup
    for link in main.find_all("a", href=True):
        full = urljoin(BASE_URL, link["href"]).rstrip("/")
        if full.startswith(prefix + "/") and full not in seen and full != prefix:
            seen.add(full)
            children.append(full)
    return children[:6]  # cap to avoid runaway crawling on huge hubs


def parse_condition_page(soup: BeautifulSoup, name: str, url: str, allow_hub_follow=True) -> dict:
    for selector in ["[class*='feedback']", "[class*='rating']", "[class*='share']",
                      "[id*='feedback']", "nav", "header", "footer",
                      "[class*='breadcrumb']", "[class*='cookie']", "[class*='banner']"]:
        for el in soup.select(selector):
            el.decompose()

    h1 = soup.find("h1")
    title = clean_text(h1.get_text()) if h1 else name

    symptoms, causes, warnings, recommendations = "", "", "", ""
    for heading in soup.find_all(["h2", "h3"]):
        heading_text = heading.get_text().lower().strip()
        section_content = _collect_section_content(heading)
        if not section_content:
            continue
        if any(p in heading_text for p in S_PATTERNS):
            symptoms = (symptoms + "\n" + section_content).strip() if symptoms else section_content
        elif any(p in heading_text for p in C_PATTERNS):
            causes = (causes + "\n" + section_content).strip() if causes else section_content
        elif any(p in heading_text for p in W_PATTERNS):
            warnings = (warnings + "\n" + section_content).strip() if warnings else section_content
        elif any(p in heading_text for p in R_PATTERNS):
            recommendations = (recommendations + "\n" + section_content).strip() if recommendations else section_content

    care_card_text = _extract_care_cards(soup)
    if care_card_text and care_card_text not in warnings:
        warnings = (warnings + "\n" + care_card_text).strip() if warnings else care_card_text

    is_hub_page = False
    body_word_count = len(soup.get_text().split())
    if allow_hub_follow and not any([symptoms, causes, warnings, recommendations]) and body_word_count < 400:
        children = _find_child_condition_links(soup, url)
        if children:
            is_hub_page = True
            merged = {"symptoms": symptoms, "causes": causes, "warnings": warnings, "recommendations": recommendations}
            for child_url in children:
                child_soup = fetch_html(child_url)
                if not child_soup:
                    continue
                cd = parse_condition_page(child_soup, name, child_url, allow_hub_follow=False)
                for field in ["symptoms", "causes", "warnings", "recommendations"]:
                    if cd[field]:
                        merged[field] = (merged[field] + "\n[" + cd["condition"] + "] " + cd[field]).strip() if merged[field] else "[" + cd["condition"] + "] " + cd[field]
            symptoms, causes, warnings, recommendations = merged["symptoms"], merged["causes"], merged["warnings"], merged["recommendations"]

    return {
        "condition": title,
        "symptoms": symptoms or None,
        "causes": causes or None,
        "warnings": warnings or None,
        "recommendations": recommendations or None,
        "url": url,
        "is_hub_page": is_hub_page,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="nhs_conditions.csv")
    ap.add_argument("--output", default="nhs_conditions_filled.csv")
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    for col in ["symptoms", "causes", "warnings", "recommendations"]:
        if col not in df.columns:
            df[col] = None
    if "url" not in df.columns:
        df["url"] = None
    if "is_hub_page" not in df.columns:
        df["is_hub_page"] = False

    to_fix = df[df[["symptoms", "causes", "warnings", "recommendations"]].isnull().any(axis=1)]
    logger.info(f"{len(to_fix)} / {len(df)} rows have at least one missing field. Re-crawling index for URLs...")

    name_to_url = build_index_map()

    for i, (idx, row) in enumerate(to_fix.iterrows(), 1):
        name = row["condition"]
        url = name_to_url.get(name)
        if not url:
            # try a loose match (curly vs straight apostrophes, case, trailing punctuation)
            norm = lambda s: re.sub(r"[^a-z0-9]", "", str(s).lower())
            for cand_name, cand_url in name_to_url.items():
                if norm(cand_name) == norm(name):
                    url = cand_url
                    break
        if not url:
            logger.warning(f"[{i}/{len(to_fix)}] No URL match found for '{name}', skipping.")
            continue

        logger.info(f"[{i}/{len(to_fix)}] Re-scraping: {name} ({url})")
        soup = fetch_html(url)
        if not soup:
            continue
        data = parse_condition_page(soup, name, url)

        # only overwrite fields that were actually missing - never clobber good existing data
        for field in ["symptoms", "causes", "warnings", "recommendations"]:
            if pd.isnull(df.at[idx, field]) and data[field]:
                df.at[idx, field] = data[field]
        df.at[idx, "url"] = url
        df.at[idx, "is_hub_page"] = data["is_hub_page"]

        if i % 10 == 0:
            df.to_csv(args.output, index=False, encoding="utf-8-sig")
            logger.info(f"  [Progress] saved {i}/{len(to_fix)} to '{args.output}'")
        time.sleep(1.5)

    df.to_csv(args.output, index=False, encoding="utf-8-sig")
    still_missing = df[df[["symptoms", "causes", "warnings", "recommendations"]].isnull().any(axis=1)]
    logger.info(f"Done. Saved to '{args.output}'. {len(still_missing)} rows still have a missing field "
                f"(likely genuine hub/guide pages worth reviewing manually - see is_hub_page column).")


if __name__ == "__main__":
    main()
