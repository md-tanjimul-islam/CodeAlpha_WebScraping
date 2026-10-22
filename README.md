# CodeAlpha_WebScraping

**Task 1: Web Scraping | CodeAlpha Data Analytics Internship**

---

## What This Project Does
This project is a Python web scraper that collects PC game data from the **Steam store** and saves it as clean CSV files. The data feeds the next two internship tasks: Exploratory Data Analysis (Task 2) and Sentiment Analysis (Task 4).

It collects two things:
1. **Game metadata** from Steam's top-sellers list: title, release date, prices, discount, review summary, and total review count.
2. **User reviews** for each of those games: review text, whether the player recommended the game, playtime, helpful votes, and date.

## What I Built
- A `SteamDataScraper` class built on `requests` and `BeautifulSoup`.
- A session with realistic browser **User-Agent headers**, an age-gate cookie, and **automatic retries** with exponential backoff for rate-limit and server errors (HTTP 429, 500, 502, 503, 504).
- **Polite rate limiting:** a random 1.5-3 second pause after every request.
- A **synthetic fallback generator** that produces 100 games and 1,500 reviews in the exact same schema. It runs with `--fallback`, and it also starts automatically if the live scrape returns nothing, so the pipeline never ends empty-handed.

## How It Works
```
Steam top-sellers search endpoint (JSON containing an HTML fragment)
        |
        v
BeautifulSoup parses each result row  ->  steam_games_metadata.csv
        |
        v   (app_id of every scraped game)
Steam public appreviews endpoint (JSON, no API key)
        |
        v
Clean review text, convert playtime to hours  ->  steam_user_reviews.csv
```

**HTML parsing map (game metadata):**

| Field | Where it comes from |
|---|---|
| `app_id` | `data-ds-appid` attribute on `a.search_result_row` |
| `title` | `span.title` |
| `release_date` | `div.search_released` |
| `discount_pct` | `div.discount_pct` |
| `original_price` / `final_price` | `div.discount_original_price` / `div.discount_final_price` |
| `review_summary`, `total_reviews` | `data-tooltip-html` on `span.search_review_summary`, split and parsed with a regex |

**Reviews:** for each `app_id`, the scraper calls `appreviews/<app_id>?json=1`, then keeps the review text, the thumbs-up flag as `recommended`, playtime converted from minutes to hours, helpful votes, and the post date.

## Project Structure
```
CodeAlpha_WebScraping/
├── data/                       # generated CSV files
│   ├── steam_games_metadata.csv
│   └── steam_user_reviews.csv
├── src/scraper.py
├── requirements.txt
├── .gitignore
└── README.md
```

## How to Run
```bash
git clone https://github.com/md-tanjimul-islam/CodeAlpha_WebScraping.git
cd CodeAlpha_WebScraping
python -m venv .venv
.venv\Scripts\activate          # Windows  (Mac/Linux: source .venv/bin/activate)
pip install -r requirements.txt
```

Then pick one:
```bash
# Live scrape (needs internet)
python src/scraper.py --games 50 --reviews-per-game 20

# Synthetic data (offline testing, 100 games + 1,500 reviews)
python src/scraper.py --fallback
```

| Option | Meaning | Default |
|---|---|---|
| `--games` | number of top sellers to scrape | 50 |
| `--reviews-per-game` | reviews to fetch per game | 20 |
| `--fallback` | skip the network and generate synthetic data | off |

## Dataset Schema

**`data/steam_games_metadata.csv`**

| Column | Description |
|---|---|
| app_id | Steam application ID |
| title | Game title |
| release_date | Release date as shown on the store |
| original_price | Price before discount (USD) |
| final_price | Current price |
| discount_pct | Discount percentage (0 if none) |
| review_summary | Steam label, e.g. "Very Positive" |
| total_reviews | Total number of user reviews |

**`data/steam_user_reviews.csv`**

| Column | Description |
|---|---|
| review_id | Unique review ID |
| app_id | Game ID (joins to the metadata file) |
| title | Game title |
| review_text | Review body |
| recommended | True if the player gave a thumbs-up |
| playtime_hours | Author's total playtime in hours |
| helpful_votes | Number of helpful votes |
| date_posted | Posting date (YYYY-MM-DD) |

## Important Note on Data Origin
If you run with `--fallback` (or the scraper switches to it automatically), the data is **synthetic**: generated with realistic distributions but not collected from Steam. The console shows a warning when this happens. State which kind of data you are using in any analysis built on it.

## Ethical Scraping Notes
- Uses only public pages and Steam's public review endpoint, with no login or API keys.
- Random 1.5-3 second delays between requests, plus backoff on errors.
- Respect Steam's Terms of Service and `robots.txt`. Keep volumes small and use the data for educational purposes only.
- Reviews are public user content. Do not redistribute them or try to identify users.

## Troubleshooting
- **Empty or partial CSV:** Steam sometimes changes its HTML. Check the CSS selectors in `_parse_row` in `src/scraper.py`.
- **HTTP 429 or timeouts:** wait a few minutes, lower `--games`, or use `--fallback`.

## Next Steps
The CSVs from this task are the input for **Task 2 (Exploratory Data Analysis)** and **Task 4 (Sentiment Analysis)**.

---
**Owner:** Md. Tanjimul Islam - CodeAlpha Intern