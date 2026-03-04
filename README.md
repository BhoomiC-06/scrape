# ScrapeFlow v2.0 — Python-Powered Web Scraper

A full-featured web scraper with a Python backend (Flask) and beautiful dark UI.

## Features
- ⚡ **requests + BeautifulSoup** — fast scraping for static/server-rendered sites
- 🎭 **Playwright** — headless Chromium for JavaScript-heavy SPAs (React, Vue, Angular)
- 🕵️ **Anti-bot evasion** — rotating User-Agents, real browser headers, stealth JS injection
- 📄 Extracts: Text, Links, Images, Headings, Meta Tags, HTML Tables, JSON-LD structured data
- 💾 Export to JSON, CSV, or TXT
- 🕐 Scrape history (stored in browser localStorage)

## Setup (one time)

```bash
# 1. Install Python dependencies
pip install flask flask-cors requests beautifulsoup4 lxml playwright

# 2. Install Playwright's headless browser
playwright install chromium
```

## Run

```bash
# Start the backend server
python server.py

# Then open index.html in your browser (just double-click it)
```

The server runs at `http://localhost:5000`

## How it works

| Site Type | Strategy Used |
|-----------|--------------|
| News sites, blogs, Wikipedia | requests + BeautifulSoup (fast) |
| React/Vue/Angular SPAs | Playwright headless Chromium |
| Sites with lazy-loaded images | Playwright (scrolls page to trigger loading) |
| Anti-bot sites (Cloudflare) | Playwright with stealth mode |

## Works great on
- Wikipedia, news sites, blogs
- E-commerce product pages
- Documentation sites
- Portfolio / company sites
- Any server-rendered HTML site

## May not work on
- Sites behind login/authentication (Netflix, banking)
- Sites with strict CAPTCHA (some Google pages)
- Sites with Cloudflare Enterprise bot protection
