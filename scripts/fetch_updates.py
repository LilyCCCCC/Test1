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
ARCHIVE_FILE = ROOT / "data" / "archive.json"

HEADERS = {
    "User-Agent": "RegulatoryMonitorBot/1.0 (+GitHub Actions)"
}


def normalize_date(value):
    if not value:
        return None

    try:
        dt = date_parser.parse(value)
        return dt.date().isoformat()
    except Exception:
        pass

    try:
        dt = parsedate_to_datetime(value)
        return dt.date().isoformat()
    except Exception:
        return None


def load_archive():
    """載入舊的歸檔資料"""
    if ARCHIVE_FILE.exists():
        try:
            data = json.loads(ARCHIVE_FILE.read_text(encoding="utf-8"))
            return data.get("items", [])
        except Exception as e:
            print(f"WARNING: Failed to load archive: {e}")
            return []
    return []


def get_unique_key(item):
    """用 URL 作為唯一鍵"""
    return item.get("url")


def merge_items(archive_items, new_items):
    """
    合併新舊資料，去重
    - 用 URL 作為唯一識別符
    - 保留新資料（因為可能有更新）
    - 保留舊資料（源 RSS 可能已刪除）
    """
    # 建立 URL -> item 的映射
    merged = {}
    
    # 先加入舊資料
    for item in archive_items:
        key = get_unique_key(item)
        if key:
            merged[key] = item
    
    # 再加入新資料（會覆蓋相同 URL 的舊資料）
    for item in new_items:
        key = get_unique_key(item)
        if key:
            merged[key] = item
    
    # 轉回列表並排序
    result = list(merged.values())
    result.sort(
        key=lambda x: (x.get("publishedAt") or "", x.get("title") or ""),
        reverse=True
    )
    
    return result


def fetch_rss(site):
    items = []
    url = site.get("rssUrl")
    print("DEBUG fetch_rss site:", site.get("id"))
    print("DEBUG fetch_rss url:", url)

    if not url:
        print("DEBUG fetch_rss skipped because rssUrl is empty")
        return items, False  # 返回 (items, success)

    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        print("DEBUG rss status:", response.status_code)
        print("DEBUG rss content-type:", response.headers.get("content-type"))

        feed = feedparser.parse(response.content)

        print("DEBUG feed bozo:", getattr(feed, "bozo", None))
        print("DEBUG feed entries count:", len(feed.entries))

        if not feed.entries:
            print("WARNING: RSS returned no entries for", site.get("id"))
            return items, False

        for entry in feed.entries[:50]:
            published = normalize_date(
                getattr(entry, "published", None)
                or getattr(entry, "updated", None)
                or entry.get("pubDate")
            )

            summary_html = entry.get("summary", "") or ""
            summary = BeautifulSoup(summary_html, "html.parser").get_text(" ", strip=True)

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

        return items, True  # 成功

    except Exception as e:
        print(f"ERROR fetching RSS for {site.get('id')}: {e}")
        return items, False  # 失敗


def fetch_webpage(site):
    items = []
    list_url = site.get("listUrl") or site.get("baseUrl")
    selectors = site.get("selectors", {})

    print("DEBUG fetch_webpage site:", site.get("id"))
    print("DEBUG fetch_webpage list_url:", list_url)

    if not list_url or not selectors:
        print("DEBUG fetch_webpage skipped because listUrl or selectors missing")
        return items, False

    try:
        response = requests.get(list_url, headers=HEADERS, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        nodes = soup.select(selectors.get("item", ""))[:50]

        print("DEBUG webpage nodes count:", len(nodes))

        if not nodes:
            print("WARNING: Webpage returned no nodes for", site.get("id"))
            return items, False

        for node in nodes:
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

        return items, True  # 成功

    except Exception as e:
        print(f"ERROR fetching webpage for {site.get('id')}: {e}")
        return items, False  # 失敗


def main():
    groups = json.loads(SITES_FILE.read_text(encoding="utf-8"))
    print("DEBUG groups loaded:", len(groups))

    # 1. 載入舊的歸檔資料
    archive_items = load_archive()
    print(f"DEBUG archive loaded: {len(archive_items)} items")

    all_new_items = []
    errors = []

    # 2. 抓取所有新資料
    for group in groups:
        print("DEBUG group:", group.get("groupId"), "enabled=", group.get("enabled", True))

        if not group.get("enabled", True):
            continue

        children = group.get("children", [])
        print("DEBUG children count:", len(children))

        for site in children:
            print(
                "DEBUG site:",
                site.get("id"),
                "enabled=",
                site.get("enabled", True),
                "type=",
                site.get("type"),
            )

            if not site.get("enabled", True):
                continue

            if site.get("type") == "rss":
                items, success = fetch_rss(site)
                print("DEBUG fetched rss items:", site.get("id"), len(items), "success=", success)
                if success:
                    all_new_items.extend(items)
                else:
                    errors.append({
                        "groupId": group.get("groupId"),
                        "siteId": site.get("id"),
                        "error": "RSS fetch failed - keeping archived data"
                    })

            elif site.get("type") == "webpage":
                items, success = fetch_webpage(site)
                print("DEBUG fetched webpage items:", site.get("id"), len(items), "success=", success)
                if success:
                    all_new_items.extend(items)
                else:
                    errors.append({
                        "groupId": group.get("groupId"),
                        "siteId": site.get("id"),
                        "error": "Webpage fetch failed - keeping archived data"
                    })

    # 3. 合併舊資料 + 新資料（去重）
    merged_items = merge_items(archive_items, all_new_items)
    print(f"DEBUG merged items: {len(merged_items)}")

    # 4. 分別保存
    # a. 保存到 archive.json（用於容錯恢復）
    archive_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(merged_items),
        "items": merged_items
    }
    ARCHIVE_FILE.write_text(
        json.dumps(archive_payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"DEBUG saved archive: {ARCHIVE_FILE}")

    # b. 保存到 latest.json（網站用）
    latest_payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "count": len(merged_items),
        "errors": errors,
        "items": merged_items
    }
    OUTPUT_FILE.write_text(
        json.dumps(latest_payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"DEBUG saved latest: {OUTPUT_FILE}")

    print(f"DEBUG final count: {len(merged_items)}")
    print(f"DEBUG errors count: {len(errors)}")


if __name__ == "__main__":
    main()
