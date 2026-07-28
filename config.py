"""
Configuration for the NHS Inform scraper.
"""

# MongoDB settings
MONGO_URI = "mongodb://localhost:27017"
DB_NAME = "nhs_inform"
COLLECTION_NAME = "conditions"

# NHS Inform URLs
BASE_URL = "https://www.nhsinform.scot"
INDEX_URL = "https://www.nhsinform.scot/illnesses-and-conditions/a-to-z/"

# Scraping settings
REQUEST_DELAY = 1.5  # seconds between requests (polite crawling)
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds to wait before retrying a failed request

# Browser-like headers to avoid being blocked
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Section heading patterns for content extraction (case-insensitive matching)
SYMPTOM_HEADINGS = ["symptoms", "signs and symptoms", "symptom"]
CAUSE_HEADINGS = ["causes", "cause", "what causes", "risk factors"]
WARNING_HEADINGS = [
    "when to get help",
    "when to see a gp",
    "when to seek medical advice",
    "when to get medical help",
    "warning signs",
    "complications",
    "when to go to a&e",
    "when to call 999",
    "urgent advice",
]
RECOMMENDATION_HEADINGS = [
    "treatment",
    "treatments",
    "self-help",
    "self help",
    "living with",
    "managing",
    "prevention",
    "how to treat",
    "things you can do",
    "recommendations",
]
