# NHS Inform Scraper

Scrapes medical conditions from [NHS Inform Scotland's A–Z index](https://www.nhsinform.scot/illnesses-and-conditions/a-to-z/) and stores structured data in MongoDB.

## What It Extracts

For each condition, the scraper extracts:

| Field             | Description                                          |
|-------------------|------------------------------------------------------|
| `title`           | Condition name (e.g., "Asthma")                      |
| `url`             | Source URL on NHS Inform                              |
| `overview`        | Introductory text before the first section            |
| `symptoms`        | Content from "Symptoms" sections                     |
| `causes`          | Content from "Causes" / "Risk factors" sections      |
| `warnings`        | "When to get help" / urgent care advice              |
| `recommendations` | Treatment, self-help, prevention advice              |
| `scraped_at`      | ISO timestamp of when the page was scraped           |

## Prerequisites

- **Python 3.12+**
- **MongoDB** running locally (default `localhost:27017`) or a remote instance

## Setup

```bash
# Install dependencies
python -m pip install -r requirements.txt
```

## Usage

```bash
# Scrape all conditions (full run)
python main.py

# Test with first 5 conditions
python main.py --limit 5

# Force re-scrape already stored conditions
python main.py --force

# Use a custom MongoDB connection
python main.py --mongo-uri "mongodb://user:pass@host:27017"

# Adjust request delay (default 1.5s)
python main.py --delay 2.0

# Verbose logging
python main.py --limit 3 -v
```

## Project Structure

```
├── config.py                  # All configuration (MongoDB, URLs, patterns)
├── main.py                    # CLI entry point / orchestrator
├── requirements.txt           # Python dependencies
├── README.md                  # This file
├── scraper/
│   ├── __init__.py
│   ├── index_scraper.py       # A-Z index → list of conditions
│   ├── condition_scraper.py   # Condition page → structured dict
│   └── utils.py               # HTTP fetch, retry, text cleaning
└── storage/
    ├── __init__.py
    └── mongo_store.py         # MongoDB upsert / batch operations
```

## MongoDB Document Schema

```json
{
  "_id": "ObjectId(...)",
  "title": "Asthma",
  "url": "https://www.nhsinform.scot/illnesses-and-conditions/lungs-and-airways/asthma",
  "overview": "Asthma is a common lung condition that causes...",
  "symptoms": "The main symptoms of asthma are...",
  "causes": "Asthma is caused by swelling of the breathing tubes...",
  "warnings": "Call 999 or go to A&E immediately if...",
  "recommendations": "The aim of treatment is to...",
  "scraped_at": "2026-07-16T17:00:00+00:00"
}
```

A unique index is created on the `url` field, so re-running the scraper updates existing documents instead of creating duplicates.
