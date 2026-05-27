# Test1
Test
# GitHub 多來源法規消息監測 App 架構

這個版本設計成：
- 使用 **GitHub Actions 每小時更新一次**
- 前端部署於 **GitHub Pages**
- 支援 **多網站來源**，後續可透過 `sites.json` 持續新增
- 每個網站可指定抓取方式：`rss` 或 `webpage`
- 使用者可在前端 **單來源搜尋** 或 **多來源同時搜尋**
- 可用 **關鍵字 + 日期區間** 篩選，並顯示 **連結 + 摘要/部分內文**

## 整體架構

```text
GitHub Repository
├─ index.html                 # 前端畫面（GitHub Pages）
├─ sites.json                 # 多來源設定檔
├─ data/
│  └─ latest.json             # GitHub Actions 每小時更新的彙整結果
├─ scripts/
│  └─ fetch_updates.py        # 抓取 RSS / 網頁新聞頁，輸出 latest.json
└─ .github/workflows/
   └─ hourly-update.yml       # 每小時執行一次抓取
```

## 運作方式

1. GitHub Actions 每小時觸發一次 workflow。
2. workflow 執行 `scripts/fetch_updates.py`。
3. Python 讀取 `sites.json`。
4. 每個來源依 `type` 決定抓取方式：
   - `rss`: 讀 RSS feed
   - `webpage`: 抓公告/新聞列表頁，依 CSS selector 擷取
5. 所有結果整理成統一格式，輸出到 `data/latest.json`。
6. workflow 自動 commit 更新後的 JSON。
7. GitHub Pages 上的 `index.html` 讀取 `sites.json` 與 `data/latest.json`，提供關鍵字、日期區間、單站/多站搜尋。

## sites.json 設計

每個網站來源一筆設定：

```json
[
  {
    "id": "fda-news-events",
    "name": "FDA News & Events",
    "region": "US",
    "baseUrl": "https://www.fda.gov/news-events",
    "type": "rss",
    "rssUrl": "https://www.fda.gov/about-fda/contact-fda/stay-informed/rss-feeds/press-releases/rss.xml",
    "enabled": true,
    "tags": ["drug", "device", "regulatory"]
  },
  {
    "id": "example-web-source",
    "name": "Example Web Source",
    "region": "APAC",
    "baseUrl": "https://example.com/news",
    "type": "webpage",
    "listUrl": "https://example.com/news",
    "selectors": {
      "item": ".news-list .item",
      "title": "a",
      "link": "a",
      "date": ".date",
      "summary": ".summary"
    },
    "enabled": true,
    "tags": ["gmp", "inspection"]
  }
]
```

## 統一輸出格式 data/latest.json

```json
{
  "generatedAt": "2026-05-27T00:00:00Z",
  "items": [
    {
      "siteId": "fda-news-events",
      "siteName": "FDA News & Events",
      "region": "US",
      "title": "Example title",
      "url": "https://www.fda.gov/example",
      "publishedAt": "2026-05-26",
      "excerpt": "Summary text...",
      "sourceType": "rss"
    }
  ]
}
```

## 前端搜尋模式

- **單來源搜尋**：選擇一個網站，只搜尋該網站結果。
- **多來源搜尋**：選擇多個網站，或直接勾選「全部來源」。
- **關鍵字搜尋**：支援單字或多組關鍵字（逗號分隔）。
- **日期區間搜尋**：比對 `publishedAt` 欄位。

## 為什麼這版適合 GitHub

- GitHub Actions 可以用 cron 排程每小時執行一次。
- GitHub Pages 適合部署純前端與 JSON 檔。
- 抓取結果存成 JSON，可避免前端直接跨站抓資料的 CORS 問題。
- 後續加網站，只要更新 `sites.json` 與必要 selector。

## 限制

- 不是即時查詢；資料是上一次排程抓取的結果。
- 若目標網站改版，`webpage` 類型的 selector 可能要調整。
- GitHub Actions 適合中小規模多站監測，但不適合重度爬蟲、登入、JavaScript-heavy 網站。

## 下一步建議

1. 先收集第一批網站來源並分類成 `rss` / `webpage`
2. 先上線 FDA + EMA + 1~2 個 APAC 站點
3. 驗證抓取穩定性後，再逐步擴充 PMDA / ASEAN 更多來源
