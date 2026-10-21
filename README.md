# CodeAlpha_WebScraping

Web scraper for the **CodeAlpha Data Analytics Internship (Task 1)**. It collects PC game metadata and user reviews from Steam and saves them as clean CSVs for downstream Exploratory Data Analysis and Sentiment Analysis.

## Overview
- Scrapes Steam's **top sellers** list (title, release date, pricing, discount, review summary).
- Fetches **user reviews** per game (text, recommendation, playtime, helpful votes, date).
- Includes retry logic, rotating User-Agents, and randomized delays.
- A `--fallback` mode generates a realistic synthetic dataset (100 games, 1,500 reviews) when the network is blocked.

## HTML Parsing Architecture
```
Search results JSON  ->  results_html fragment  ->  BeautifulSoup
  a.search_result_row[data-ds-appid]   -> app_id
  span.title                           -> title
  div.search_released                  -> release_date
  div.discount_pct                     -> discount_pct
  div.discount_original_price          -> original_price
  div.discount_final_price             -> final_price
  span.search_review_summary
     [data-tooltip-html]               -> review_summary, total_reviews (regex)

appreviews/<app_id>?json=1 (JSON)      -> review rows -> pandas
```

## Setup
```bash
git clone https://github.com/<your-username>/CodeAlpha_WebScraping.git
cd CodeAlpha_WebScraping
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage
```bash
python src/scraper.py --games 50 --reviews-per-game 20   # live scrape
python src/scraper.py --fallback                          # synthetic data
```
If the live scrape returns nothing, the script switches to the fallback automatically.

## Dataset Schema

**`data/steam_games_metadata.csv`**

| Column | Description |
|---|---|
| app_id | Steam application ID |
| title | Game title |
| release_date | Release date as shown on the store |
| original_price | Price before discount (store currency, USD with `cc=us`) |
| final_price | Current price |
| discount_pct | Discount percentage (0 if none) |
| review_summary | Steam label, e.g. "Very Positive" |
| total_reviews | Total number of user reviews |

**`data/steam_user_reviews.csv`**

| Column | Description |
|---|---|
| review_id | Unique review ID |
| app_id | Game ID (joins to metadata) |
| title | Game title |
| review_text | Review body |
| recommended | True if thumbs-up |
| playtime_hours | Author's total playtime in hours |
| helpful_votes | Number of helpful votes |
| date_posted | Posting date (YYYY-MM-DD) |

## Ethical Scraping Notes
- Uses only public pages and Steam's public review endpoint, with no login or API keys.
- Randomized 1.5-3 second delays between requests and exponential backoff on errors.
- Respect Steam's Terms of Service and `robots.txt`; keep volumes small and use the data for educational purposes only.
- Reviews are public user content. Do not redistribute or attempt to identify users.
- The synthetic dataset is artificial and must not be presented as real data.

## Next Steps
EDA (price vs. rating, release trends) and sentiment analysis on `review_text`.