"""Steam web scraper (requests + BeautifulSoup) with synthetic fallback.

Usage:
    python src/scraper.py --games 50 --reviews-per-game 20
    python src/scraper.py --fallback
"""
import argparse
import logging
import random
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("steam_scraper")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEARCH_URL = "https://store.steampowered.com/search/results/"
REVIEW_URL = "https://store.steampowered.com/appreviews/{app_id}"

GAME_COLS = ["app_id", "title", "release_date", "original_price", "final_price",
             "discount_pct", "review_summary", "total_reviews"]
REVIEW_COLS = ["review_id", "app_id", "title", "review_text", "recommended",
               "playtime_hours", "helpful_votes", "date_posted"]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
]


class SteamDataScraper:
    """Scrapes Steam top sellers (HTML) and user reviews (public JSON/HTML endpoint)."""

    def __init__(self, delay=(1.5, 3.0), timeout=15):
        self.delay, self.timeout = delay, timeout
        self.session = requests.Session()
        retry = Retry(total=4, backoff_factor=1.5,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET"])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.session.headers.update({
            "User-Agent": random.choice(USER_AGENTS),
            "Accept-Language": "en-US,en;q=0.9",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
        })
        # Skip age-gate and set English/US store
        self.session.cookies.update({"birthtime": "568022401", "mature_content": "1",
                                     "wants_mature_content": "1"})

    def _sleep(self):
        time.sleep(random.uniform(*self.delay))

    def _get(self, url, **kwargs):
        resp = self.session.get(url, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        self._sleep()
        return resp

    # ---------- parsing helpers ----------
    @staticmethod
    def _price(text):
        """'$19.99' / '₹ 1,299' / 'Free To Play' -> float (0.0 if free/missing)."""
        if not text:
            return 0.0
        m = re.search(r"(\d[\d,]*\.?\d*)", text.replace(",", ""))
        return float(m.group(1)) if m else 0.0

    @staticmethod
    def _parse_reviews_tooltip(tooltip):
        """Parse '<br>' tooltips like 'Very Positive<br>92% of the 1,234 user reviews...'"""
        if not tooltip:
            return None, 0
        parts = tooltip.split("<br>")
        summary = parts[0].strip() or None
        m = re.search(r"of the ([\d,]+)", parts[1] if len(parts) > 1 else "")
        return summary, int(m.group(1).replace(",", "")) if m else 0

    # ---------- game metadata ----------
    def scrape_top_sellers(self, n_games=50):
        """Page through the top-sellers search (HTML fragments) and parse each row."""
        games, start = [], 0
        while len(games) < n_games:
            params = {"query": "", "start": start, "count": 50, "filter": "topsellers",
                      "infinite": 1, "cc": "us", "l": "english", "category1": 998}
            try:
                payload = self._get(SEARCH_URL, params=params).json()
            except (requests.RequestException, ValueError) as exc:
                log.error("Search request failed at start=%d: %s", start, exc)
                break
            soup = BeautifulSoup(payload.get("results_html", ""), "html.parser")
            rows = soup.select("a.search_result_row")
            if not rows:
                break
            for row in rows:
                rec = self._parse_row(row)
                if rec:
                    games.append(rec)
            log.info("Parsed %d games so far", len(games))
            start += 50
        df = pd.DataFrame(games[:n_games], columns=GAME_COLS).drop_duplicates("app_id")
        return df.reset_index(drop=True)

    def _parse_row(self, row):
        app_id = (row.get("data-ds-appid") or "").split(",")[0]
        title = row.select_one("span.title")
        if not app_id or not title:
            return None
        release = row.select_one("div.search_released")
        disc = row.select_one("div.search_discount_block")
        discount_pct, original, final = 0, 0.0, 0.0
        if disc:
            pct = disc.select_one("div.discount_pct")
            discount_pct = abs(int(re.sub(r"[^\d-]", "", pct.text))) if pct and pct.text.strip() else 0
            orig = disc.select_one("div.discount_original_price")
            fin = disc.select_one("div.discount_final_price")
            final = self._price(fin.text if fin else "")
            original = self._price(orig.text) if orig else final
        summary_tag = row.select_one("span.search_review_summary")
        summary, total = self._parse_reviews_tooltip(
            summary_tag.get("data-tooltip-html") if summary_tag else None)
        return {
            "app_id": int(app_id), "title": title.text.strip(),
            "release_date": release.text.strip() if release else None,
            "original_price": original, "final_price": final,
            "discount_pct": discount_pct, "review_summary": summary,
            "total_reviews": total,
        }

    # ---------- user reviews ----------
    def scrape_reviews(self, games_df, per_game=20):
        """Fetch reviews per app_id from Steam's public appreviews JSON endpoint."""
        records = []
        for _, g in games_df.iterrows():
            params = {"json": 1, "filter": "recent", "language": "english",
                      "num_per_page": min(per_game, 100), "purchase_type": "all"}
            try:
                data = self._get(REVIEW_URL.format(app_id=g.app_id), params=params).json()
            except (requests.RequestException, ValueError) as exc:
                log.warning("Reviews failed for %s (%s): %s", g.app_id, g.title, exc)
                continue
            for r in data.get("reviews", [])[:per_game]:
                text = " ".join((r.get("review") or "").split())
                if not text:
                    continue
                records.append({
                    "review_id": r.get("recommendationid"), "app_id": int(g.app_id),
                    "title": g.title, "review_text": text,
                    "recommended": bool(r.get("voted_up")),
                    "playtime_hours": round(r.get("author", {}).get("playtime_forever", 0) / 60, 1),
                    "helpful_votes": int(r.get("votes_up", 0)),
                    "date_posted": datetime.utcfromtimestamp(r.get("timestamp_created", 0)).strftime("%Y-%m-%d"),
                })
            log.info("Reviews collected: %d (last: %s)", len(records), g.title)
        return pd.DataFrame(records, columns=REVIEW_COLS).drop_duplicates("review_id")


# ---------- synthetic fallback ----------
def generate_synthetic(n_games=100, n_reviews=1500, seed=42):
    """Statistically rich synthetic data matching the exact schema."""
    rng = np.random.default_rng(seed)
    adj = ["Dark", "Eternal", "Cyber", "Lost", "Crimson", "Silent", "Neon", "Iron", "Frozen",
           "Savage", "Hidden", "Last", "Rogue", "Mythic", "Final", "Wild"]
    noun = ["Legacy", "Frontier", "Odyssey", "Protocol", "Kingdom", "Horizon", "Siege", "Echoes",
            "Dominion", "Uprising", "Voyage", "Tactics", "Chronicles", "Survivors", "Realm", "Arena"]
    titles = list({f"{a} {n}" for a in adj for n in noun})
    rng.shuffle(titles)
    titles = titles[:n_games]

    # Quality drives sentiment; popularity is log-normal (heavy-tailed like real stores)
    quality = np.clip(rng.beta(5, 2, n_games), 0.15, 0.98)
    total = np.clip(rng.lognormal(7.5, 1.6, n_games), 25, 2_000_000).astype(int)
    base = rng.choice([0, 4.99, 9.99, 14.99, 19.99, 29.99, 39.99, 49.99, 59.99], n_games,
                      p=[.1, .08, .14, .12, .16, .14, .1, .08, .08])
    disc = np.where((base > 0) & (rng.random(n_games) < .4),
                    rng.choice([10, 15, 20, 25, 33, 50, 60, 75, 80], n_games), 0)
    final = np.round(base * (1 - disc / 100), 2)

    def summary(q, t):
        if t < 50: return "Mixed" if q < .6 else "Positive"
        for cut, lab in [(.93, "Overwhelmingly Positive"), (.85, "Very Positive"), (.75, "Positive"),
                         (.65, "Mostly Positive"), (.45, "Mixed"), (.30, "Mostly Negative")]:
            if q >= cut: return lab
        return "Very Negative"

    start = datetime(2015, 1, 1)
    release = [(start + timedelta(days=int(d))).strftime("%b %d, %Y")
               for d in rng.integers(0, 3800, n_games)]
    games = pd.DataFrame({
        "app_id": rng.choice(np.arange(100000, 2500000, 10), n_games, replace=False),
        "title": titles, "release_date": release, "original_price": base,
        "final_price": final, "discount_pct": disc,
        "review_summary": [summary(q, t) for q, t in zip(quality, total)],
        "total_reviews": total,
    })[GAME_COLS]

    pos = ["Absolutely loved the {a}. Gameplay is smooth and the {b} kept me hooked for hours.",
           "Best purchase this year, the {a} is stunning and the {b} feels rewarding.",
           "Great value. {a} and {b} are both top tier, would recommend to friends.",
           "Solid game with a fantastic {a}. The {b} is addictive.",
           "Hidden gem! The {a} surprised me and the {b} is polished."]
    neg = ["Disappointing. The {a} is broken and the {b} gets repetitive fast.",
           "Not worth the price, {a} feels unfinished and the {b} is full of bugs.",
           "Crashes constantly. The {a} is poor and {b} needs a serious rework.",
           "Refunded after two hours, the {a} was bland and the {b} was frustrating.",
           "Mixed feelings: nice {a}, but the {b} ruins the experience."]
    aspects = ["story", "graphics", "soundtrack", "combat", "multiplayer", "controls",
               "level design", "progression system", "performance", "art style"]

    weights = total / total.sum()
    idx = rng.choice(n_games, n_reviews, p=weights)
    reviews = []
    for i, gi in enumerate(idx):
        rec = rng.random() < quality[gi]
        a, b = rng.choice(aspects, 2, replace=False)
        text = rng.choice(pos if rec else neg).format(a=a, b=b)
        if rng.random() < .3:
            text += " " + rng.choice(["Worth every penny.", "Needs more content.", "Devs listen to feedback.",
                                      "Optimization could be better.", "Played it with friends, great fun.",
                                      "Update 1.2 fixed most issues."])
        released = datetime.strptime(release[gi], "%b %d, %Y")
        days = max((datetime(2026, 10, 1) - released).days, 1)
        reviews.append({
            "review_id": 90000000 + i, "app_id": int(games.app_id[gi]), "title": titles[gi],
            "review_text": text, "recommended": bool(rec),
            "playtime_hours": round(float(rng.lognormal(2.6 if rec else 1.8, 1.1)), 1),
            "helpful_votes": int(rng.negative_binomial(1, 0.25 if rec else 0.15)),
            "date_posted": (released + timedelta(days=int(rng.integers(0, days)))).strftime("%Y-%m-%d"),
        })
    return games, pd.DataFrame(reviews, columns=REVIEW_COLS)


def save(games, reviews):
    DATA_DIR.mkdir(exist_ok=True)
    games.to_csv(DATA_DIR / "steam_games_metadata.csv", index=False)
    reviews.to_csv(DATA_DIR / "steam_user_reviews.csv", index=False)
    log.info("Saved %d games and %d reviews to %s", len(games), len(reviews), DATA_DIR)


def main():
    p = argparse.ArgumentParser(description="Steam metadata + review scraper")
    p.add_argument("--games", type=int, default=50, help="number of top sellers to scrape")
    p.add_argument("--reviews-per-game", type=int, default=20)
    p.add_argument("--fallback", action="store_true", help="skip network, generate synthetic data")
    a = p.parse_args()

    if a.fallback:
        save(*generate_synthetic())
        return
    scraper = SteamDataScraper()
    games = scraper.scrape_top_sellers(a.games)
    if games.empty:
        log.warning("Live scrape returned no games; switching to synthetic fallback.")
        save(*generate_synthetic())
        return
    reviews = scraper.scrape_reviews(games, a.reviews_per_game)
    if reviews.empty:
        log.warning("No reviews retrieved; using synthetic reviews for scraped games is skipped, "
                    "switching fully to synthetic fallback.")
        save(*generate_synthetic())
        return
    save(games, reviews)


if __name__ == "__main__":
    main()