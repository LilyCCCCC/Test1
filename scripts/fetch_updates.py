import json
from pathlib import Path
from urllib.parse import urljoin
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone

import requests
import feedparser
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

ROOT = Path(__file__).resolve().parents[1]
SITES_FILE = ROOT / "sites.json"
OUTPUT_FILE = ROOT / "data" / "latest.json"
HEADERS = {"User-Agent": "RegulatoryMonitorBot/1.0 (+GitHub Actions)"}


def normalize_date(value):
    if not value:
        return None
    try:
        dt = date_parser.parse(value)
        return dt.date().isoformat()
    except Exception:
        try:
            dt = parsedate_to_datetime(value)
            return dt.date().isoformat()
        except Exception:
            return None


def fetch_rss(site):
    items = []
    url = site.get("rssUrl")
    if not url:
        return items

    feed = feedparser.parse(url)
    for entry in feed.entries[:50]:
        published = normalize_date(
            getattr(entry, "published", None)
            or getattr(entry, "updated", None)
            or entry.get("pubDate")
        )
        summary = BeautifulSoup(entry.get("summary", ""), "html.parser").get_text(" ", strip=True)
        items.append({
            "siteId": site["id"],
            "siteName": site["name"],
            "region": site.get("region", ""),
            "title": entry.get("title", "").strip(),
            "url": entry.get("link", "").strip(),
            "publishedAt": published,
            "excerpt": summary[:500],
            "sourceType": "rss"
        })
    return items


def fetch_webpage(site):
    items = []
    list_url = site.get("listUrl") or site.get("baseUrl")
    selectors = site.get("selectors", {})
    if not list_url or not selectors:
        return items

    response = requests.get(list_url, headers=HEADERS, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    for node in soup.select(selectors.get("item", ""))[:50]:
        title_el = node.select_one(selectors.get("title", "")) if selectors.get("title") else None
        link_el = node.select_one(selectors.get("link", "")) if selectors.get("link") else title_el
        date_el = node.select_one(selectors.get("date", "")) if selectors.get("date") else None
        summary_el = node.select_one(selectors.get("summary", "")) if selectors.get("summary") else None

        title = title_el.get_text(" ", strip=True) if title_el else ""
        href = link_el.get("href", "").strip() if link_el else ""
        full_url = urljoin(list_url, href) if href else list_url
        published = normalize_date(date_el.get_text(" ", strip=True) if date_el else None)
        summary = summary_el.get_text(" ", strip=True) if summary_el else ""

        if title:
            items.append({
                "siteId": site["id"],
                "siteName": site["name"],
                "region": site.get("region", ""),
                "title": title,
                "url": full_url,
                "publishedAt": published,
                "excerpt": summary[:500],
                "sourceType": "webpage"
            })
    return items


def main():
    sites = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    all_items = []
    errors = []

    for site in sites:
        if not site.get("enabled", True):
            continue
        try:
            if site.get("type") == "rss":
                all_items.extend(fetch_rss(site))
            elif site.get("type") == "webpage":
                all_items.extend(fetch_webpage(site))
        except Exception as exc:
            errors.append({"siteId": site.get("id"), "error": str(exc)})

    all_items.sort(
        key=lambda x: (x.get("publishedAt") or "", x.get("title") or ""),
        reverse=True
    )

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(all_items),
        "errors": errors,
        "items": all_items
    }

    OUTPUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


if __name__ == "__main__":
    main()
