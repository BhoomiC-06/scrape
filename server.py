"""
ScrapeFlow - Python Backend Server
===================================
Supports:
  - Static sites   → requests + BeautifulSoup
  - JS-heavy sites → Playwright (headless Chromium)
  - Anti-bot sites → rotating User-Agents + headers spoofing

Run:
    pip install flask flask-cors requests beautifulsoup4 lxml playwright
    playwright install chromium
    python server.py
"""

import json
import re
import time
import random
import threading
from urllib.parse import urljoin, urlparse

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ─── User-Agent pool ──────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0",
]

HEADERS_BASE = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# ─── Scrape logic ─────────────────────────────────────────────────────────────

def get_headers():
    return {**HEADERS_BASE, "User-Agent": random.choice(USER_AGENTS)}


def scrape_with_requests(url: str):
    """Fast scrape using requests + BeautifulSoup."""
    import requests
    from bs4 import BeautifulSoup

    session = requests.Session()
    session.max_redirects = 10

    resp = session.get(
        url,
        headers=get_headers(),
        timeout=20,
        allow_redirects=True,
        verify=True,
    )
    resp.raise_for_status()
    html = resp.text
    return html, resp.url, "requests"


def scrape_with_playwright(url: str):
    """Full browser scrape using Playwright for JS-heavy sites."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
            java_script_enabled=True,
        )
        # Stealth: hide webdriver flag
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3] });
        """)
        page = ctx.new_page()
        page.goto(url, wait_until="networkidle", timeout=30000)
        # Scroll to load lazy content
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(1.5)
        html = page.content()
        final_url = page.url
        browser.close()
    return html, final_url, "playwright"


def parse_html(html: str, page_url: str, method: str) -> dict:
    """Parse HTML and extract all structured data."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    base_url = page_url

    # ── Title ──
    title = (
        (soup.find("title") or {}).get_text(strip=True)
        or (soup.find("h1") or {}).get_text(strip=True)
        or urlparse(page_url).netloc
    )

    # ── Clean text ──
    for tag in soup(["script", "style", "noscript", "svg", "iframe", "nav", "footer", "aside"]):
        tag.decompose()

    raw_text = soup.get_text(separator="\n", strip=True)
    raw_text = re.sub(r"\n{3,}", "\n\n", raw_text).strip()

    # ── Links ──
    seen_links = set()
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True).replace("\n", " ")
        if not href or href.startswith(("javascript:", "mailto:", "#", "tel:")):
            continue
        abs_href = urljoin(base_url, href)
        parsed = urlparse(abs_href)
        if parsed.scheme not in ("http", "https"):
            continue
        if abs_href not in seen_links:
            seen_links.add(abs_href)
            links.append({"text": text[:120], "href": abs_href})

    # ── Images ──
    seen_imgs = set()
    images = []
    img_attrs = ["src", "data-src", "data-lazy", "data-original", "data-srcset", "srcset"]
    for img in soup.find_all("img"):
        raw = None
        for attr in img_attrs:
            raw = img.get(attr)
            if raw:
                # handle srcset (take first URL)
                raw = raw.split(",")[0].split(" ")[0].strip()
                break
        if not raw or raw.startswith("data:"):
            continue
        src = urljoin(base_url, raw)
        if src not in seen_imgs:
            seen_imgs.add(src)
            images.append({
                "src": src,
                "alt": img.get("alt", "").strip(),
                "width": img.get("width", ""),
                "height": img.get("height", ""),
            })

    # ── Headings ──
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = tag.get_text(strip=True).replace("\n", " ")
        if text:
            headings.append({"level": tag.name.upper(), "text": text[:300]})

    # ── Meta tags ──
    metas = []
    seen_meta = set()
    for m in soup.find_all("meta"):
        charset = m.get("charset")
        name = m.get("name") or m.get("property") or m.get("http-equiv")
        content = m.get("content", "")
        if charset and "charset" not in seen_meta:
            seen_meta.add("charset")
            metas.append({"name": "charset", "content": charset})
        elif name and name not in seen_meta:
            seen_meta.add(name)
            metas.append({"name": name, "content": content[:500]})

    # ── Tables ──
    tables = []
    for tbl in soup.find_all("table")[:10]:
        rows = []
        for tr in tbl.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if cells:
                rows.append(cells)
        if rows:
            tables.append(rows)

    # ── Structured data (JSON-LD) ──
    jsonld = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            jsonld.append(json.loads(script.string or "{}"))
        except Exception:
            pass

    return {
        "url": page_url,
        "final_url": page_url,
        "title": title,
        "method": method,
        "characters": len(raw_text),
        "word_count": len(raw_text.split()),
        "text": raw_text,
        "links": links[:500],
        "images": images[:150],
        "headings": headings[:200],
        "metas": metas,
        "tables": tables,
        "jsonld": jsonld,
    }


def do_scrape(url: str) -> dict:
    """
    Try scraping strategies in order:
    1. requests (fast, works for most static sites)
    2. playwright (for JS-heavy / SPA sites)
    """
    errors = []

    # Strategy 1: requests
    try:
        html, final_url, method = scrape_with_requests(url)
        if len(html) > 500:
            result = parse_html(html, final_url, method)
            # If very little text extracted, try playwright
            if result["word_count"] > 30:
                return result
            errors.append(f"requests: got HTML but sparse content ({result['word_count']} words)")
        else:
            errors.append("requests: response too short")
    except Exception as e:
        errors.append(f"requests: {e}")

    # Strategy 2: playwright
    try:
        html, final_url, method = scrape_with_playwright(url)
        result = parse_html(html, final_url, method)
        result["fallback_errors"] = errors
        return result
    except Exception as e:
        errors.append(f"playwright: {e}")

    raise RuntimeError(" | ".join(errors))


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/scrape", methods=["POST"])
def scrape_endpoint():
    data = request.get_json(force=True)
    url = (data.get("url") or "").strip()

    if not url:
        return jsonify({"error": "No URL provided"}), 400

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        result = do_scrape(url)
        return jsonify({"ok": True, "data": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "server": "ScrapeFlow Python Backend"})


@app.route("/", methods=["GET"])
def index():
    return """
    <h2>ScrapeFlow Python Backend is running ✅</h2>
    <p>POST to <code>/scrape</code> with JSON body: <code>{"url": "https://example.com"}</code></p>
    <p>Open <strong>index.html</strong> in your browser to use the UI.</p>
    """


if __name__ == "__main__":
    print("\n" + "="*50)
    print("  ScrapeFlow Python Backend")
    print("  Running at: http://localhost:5000")
    print("  Open index.html in your browser")
    print("="*50 + "\n")
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
