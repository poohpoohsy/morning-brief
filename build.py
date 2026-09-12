"""Morning Brief - single file build.

Everything lives in here: the feed configuration, the bank list, the page
template and the daily build. Created this way so it can be set up entirely
from a phone, with one file to paste instead of nine.

On the first run it writes index.html and data/rates_manual.json for you.
After that, edit those two on GitHub directly; this file leaves them alone.

Environment:
  LLM_PROVIDER   "openai" (default) or "anthropic"
  OPENAI_API_KEY / ANTHROPIC_API_KEY
  LLM_MODEL      optional override
"""

import os, re, json, html, time, urllib.request, urllib.error
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
HK = timezone(timedelta(hours=8))
LOG = []

CFG = {
    "window_hours": 50,
    "sections": {
        "work": {
            "label": "Work",
            "max_items": 3,
            "feeds": [
                {
                    "name": "明報 經濟",
                    "url": "https://news.mingpao.com/rss/pns/s00004.xml"
                },
                {
                    "name": "明報 國際",
                    "url": "https://news.mingpao.com/rss/pns/s00014.xml"
                },
                {
                    "name": "明報 即時經濟",
                    "url": "https://news.mingpao.com/rss/ins/s00002.xml"
                },
                {
                    "name": "Fintech News HK",
                    "url": "https://fintechnews.hk/feed"
                },
                {
                    "name": "Ledger Insights",
                    "url": "https://www.ledgerinsights.com/feed/"
                },
                {
                    "name": "RTHK finance",
                    "url": "https://rthk.hk/rthk/news/rss/e_expressnews_efinance.xml"
                },
                {
                    "name": "RTHK 財經",
                    "url": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
                },
                {
                    "name": "銀行新聞 GN1",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aaastocks.com+OR+site%3Aetnet.com.hk+OR+site%3Ahkej.com+OR+site%3Ahket.com+OR+site%3Amingpao.com%29+%28%E9%8A%80%E8%A1%8C+OR+%E5%AD%98%E6%AC%BE+OR+%E9%87%91%E7%AE%A1%E5%B1%80+OR+%E8%99%9B%E6%93%AC%E9%8A%80%E8%A1%8C+OR+%E7%A9%A9%E5%AE%9A%E5%B9%A3+OR+%E4%B8%8A%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "銀行新聞 GN2",
                    "url": "https://news.google.com/rss/search?q=%28site%3Anews.now.com+OR+site%3Aquamnet.com+OR+site%3Aorientaldaily.on.cc+OR+site%3Awenweipo.com+OR+site%3Ahk.finance.yahoo.com%29+%28%E9%8A%80%E8%A1%8C+OR+%E5%AD%98%E6%AC%BE+OR+%E9%87%91%E7%AE%A1%E5%B1%80+OR+%E8%99%9B%E6%93%AC%E9%8A%80%E8%A1%8C+OR+%E7%A9%A9%E5%AE%9A%E5%B9%A3+OR+%E4%B8%8A%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "銀行新聞 GN3",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aam730.com.hk+OR+site%3Astheadline.com+OR+site%3Ahk01.com+OR+site%3Abastillepost.com+OR+site%3Ahubbis.com%29+%28%E9%8A%80%E8%A1%8C+OR+%E5%AD%98%E6%AC%BE+OR+%E9%87%91%E7%AE%A1%E5%B1%80+OR+%E8%99%9B%E6%93%AC%E9%8A%80%E8%A1%8C+OR+%E7%A9%A9%E5%AE%9A%E5%B9%A3+OR+%E4%B8%8A%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "銀行新聞 GN4",
                    "url": "https://news.google.com/rss/search?q=%28site%3Athestandard.com.hk+OR+site%3Arthk.hk%29+%28%E9%8A%80%E8%A1%8C+OR+%E5%AD%98%E6%AC%BE+OR+%E9%87%91%E7%AE%A1%E5%B1%80+OR+%E8%99%9B%E6%93%AC%E9%8A%80%E8%A1%8C+OR+%E7%A9%A9%E5%AE%9A%E5%B9%A3+OR+%E4%B8%8A%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "HK banking wide",
                    "url": "https://news.google.com/rss/search?q=Hong+Kong+bank+OR+HKMA+OR+stablecoin+when%3A2d&hl=en-HK&gl=HK&ceid=HK:en"
                }
            ],
            "include": [
                "銀行",
                "存款",
                "息",
                "滙",
                "虛擬銀行",
                "穩定幣",
                "代幣",
                "金管局",
                "上市",
                "招股",
                "資管",
                "財富",
                "保險",
                "聯儲",
                "CPI",
                "債息",
                "支付",
                "bank",
                "deposit",
                "HIBOR",
                "HKMA",
                "stablecoin",
                "token",
                "IPO",
                "fintech",
                "wealth",
                "payment",
                "Fed",
                "rate"
            ],
            "exclude": []
        },
        "smalltalk_hk": {
            "label": "Small Talk · Hong Kong",
            "max_items": 4,
            "feeds": [
                {
                    "name": "明報 經濟",
                    "url": "https://news.mingpao.com/rss/pns/s00004.xml"
                },
                {
                    "name": "明報 國際",
                    "url": "https://news.mingpao.com/rss/pns/s00014.xml"
                },
                {
                    "name": "news.gov.hk",
                    "url": "https://www.news.gov.hk/rss/news/topstories_en.xml"
                },
                {
                    "name": "商業新聞 GN1",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aaastocks.com+OR+site%3Aetnet.com.hk+OR+site%3Ahkej.com+OR+site%3Ahket.com+OR+site%3Amingpao.com%29+%28%E6%94%B6%E8%B3%BC+OR+%E6%A5%AD%E7%B8%BE+OR+%E7%B6%93%E6%BF%9F+OR+%E6%A8%93%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "商業新聞 GN2",
                    "url": "https://news.google.com/rss/search?q=%28site%3Anews.now.com+OR+site%3Aquamnet.com+OR+site%3Aorientaldaily.on.cc+OR+site%3Awenweipo.com+OR+site%3Ahk.finance.yahoo.com%29+%28%E6%94%B6%E8%B3%BC+OR+%E6%A5%AD%E7%B8%BE+OR+%E7%B6%93%E6%BF%9F+OR+%E6%A8%93%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "商業新聞 GN3",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aam730.com.hk+OR+site%3Astheadline.com+OR+site%3Ahk01.com+OR+site%3Abastillepost.com+OR+site%3Ahubbis.com%29+%28%E6%94%B6%E8%B3%BC+OR+%E6%A5%AD%E7%B8%BE+OR+%E7%B6%93%E6%BF%9F+OR+%E6%A8%93%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "商業新聞 GN4",
                    "url": "https://news.google.com/rss/search?q=%28site%3Athestandard.com.hk+OR+site%3Arthk.hk%29+%28%E6%94%B6%E8%B3%BC+OR+%E6%A5%AD%E7%B8%BE+OR+%E7%B6%93%E6%BF%9F+OR+%E6%A8%93%E5%B8%82%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                }
            ],
            "include": [
                "收購",
                "併購",
                "入主",
                "招股",
                "業績",
                "裁員",
                "擴張",
                "報告",
                "acquisition",
                "merger",
                "results",
                "expansion",
                "report"
            ],
            "exclude": []
        },
        "smalltalk_sg": {
            "label": "Small Talk · Singapore",
            "max_items": 2,
            "feeds": [
                {
                    "name": "The Independent SG",
                    "url": "https://theindependent.sg/feed/"
                },
                {
                    "name": "Workers' Party",
                    "url": "https://www.wp.sg/feed/"
                },
                {
                    "name": "SG business (GN)",
                    "url": "https://news.google.com/rss/search?q=Singapore+MAS+OR+bank+OR+economy+when%3A1d&hl=en-HK&gl=HK&ceid=HK:en"
                }
            ],
            "include": [
                "MAS",
                "minister",
                "PAP",
                "parliament",
                "budget",
                "policy",
                "bank",
                "GIC",
                "Temasek"
            ],
            "exclude": []
        },
        "personal_hk": {
            "label": "Personal · 香港民生",
            "max_items": 8,
            "feeds": [
                {
                    "name": "明報 港聞",
                    "url": "https://news.mingpao.com/rss/pns/s00002.xml"
                },
                {
                    "name": "明報 娛樂",
                    "url": "https://news.mingpao.com/rss/pns/s00016.xml"
                },
                {
                    "name": "明報 副刊",
                    "url": "https://news.mingpao.com/rss/pns/s00005.xml"
                },
                {
                    "name": "明報 即時港聞",
                    "url": "https://news.mingpao.com/rss/ins/s00001.xml"
                },
                {
                    "name": "HKFP",
                    "url": "https://hongkongfp.com/feed"
                },
                {
                    "name": "RTHK 本地",
                    "url": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml"
                },
                {
                    "name": "港聞 GN1",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aaastocks.com+OR+site%3Aetnet.com.hk+OR+site%3Ahkej.com+OR+site%3Ahket.com+OR+site%3Amingpao.com%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "港聞 GN2",
                    "url": "https://news.google.com/rss/search?q=%28site%3Anews.now.com+OR+site%3Aquamnet.com+OR+site%3Aorientaldaily.on.cc+OR+site%3Awenweipo.com+OR+site%3Ahk.finance.yahoo.com%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "港聞 GN3",
                    "url": "https://news.google.com/rss/search?q=%28site%3Aam730.com.hk+OR+site%3Astheadline.com+OR+site%3Ahk01.com+OR+site%3Abastillepost.com+OR+site%3Ahubbis.com%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "港聞 GN4",
                    "url": "https://news.google.com/rss/search?q=%28site%3Athestandard.com.hk+OR+site%3Arthk.hk%29+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "香港 wide",
                    "url": "https://news.google.com/rss/search?q=%E9%A6%99%E6%B8%AF+when%3A2d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                }
            ],
            "include": [
                "香港",
                "港",
                "市民",
                "警",
                "法院",
                "醫",
                "學校",
                "天文台",
                "展覽",
                "食",
                "藝人",
                "歌手",
                "演員",
                "逝世",
                "意外",
                "判囚",
                "被捕",
                "房屋",
                "交通"
            ],
            "exclude": [
                "工程",
                "維修",
                "改道",
                "暫停服務",
                "提早收車",
                "封路",
                "例行",
                "統計數字",
                "諮詢文件",
                "招標",
                "空缺",
                "周年報告",
                "engineering works",
                "service adjustment",
                "road closure",
                "consultation paper"
            ]
        },
        "personal_sg": {
            "label": "Personal · Singapore Government",
            "max_items": 2,
            "feeds": [
                {
                    "name": "The Independent SG",
                    "url": "https://theindependent.sg/feed/"
                },
                {
                    "name": "Workers' Party",
                    "url": "https://www.wp.sg/feed/"
                },
                {
                    "name": "SG govt (GN)",
                    "url": "https://news.google.com/rss/search?q=Singapore+minister+OR+parliament+OR+PAP+when%3A1d&hl=en-HK&gl=HK&ceid=HK:en"
                }
            ],
            "include": [
                "minister",
                "cabinet",
                "PAP",
                "WP",
                "parliament",
                "president",
                "election"
            ],
            "exclude": []
        }
    },
    "hkma": {
        "daily": "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity",
        "press": "https://api.hkma.gov.hk/public/press-releases?lang=en"
    },
    "weather": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=fnd&lang=en",
    "watched_publishers": [
        {
            "name": "AASTOCKS",
            "domain": "aastocks.com"
        },
        {
            "name": "ET Net",
            "domain": "etnet.com.hk"
        },
        {
            "name": "HKEJ 信報",
            "domain": "hkej.com"
        },
        {
            "name": "HKET 經濟日報",
            "domain": "hket.com"
        },
        {
            "name": "Ming Pao 明報",
            "domain": "mingpao.com"
        },
        {
            "name": "Now Finance",
            "domain": "news.now.com"
        },
        {
            "name": "Quamnet",
            "domain": "quamnet.com"
        },
        {
            "name": "Oriental Daily",
            "domain": "orientaldaily.on.cc"
        },
        {
            "name": "Wen Wei Po 文匯",
            "domain": "wenweipo.com"
        },
        {
            "name": "Yahoo Finance",
            "domain": "hk.finance.yahoo.com"
        },
        {
            "name": "am730",
            "domain": "am730.com.hk"
        },
        {
            "name": "Sing Tao 星島",
            "domain": "stheadline.com"
        },
        {
            "name": "HK01 香港01",
            "domain": "hk01.com"
        },
        {
            "name": "Bastille Post",
            "domain": "bastillepost.com"
        },
        {
            "name": "Hubbis",
            "domain": "hubbis.com"
        },
        {
            "name": "The Standard",
            "domain": "thestandard.com.hk"
        },
        {
            "name": "RTHK",
            "domain": "rthk.hk"
        }
    ]
}

BANKS = {
    "tenor": "3-month, new money, HKD",
    "banks": [
        {
            "name": "ZA Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://za.group/en/bank"
        },
        {
            "name": "livi Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.livibank.com/en/"
        },
        {
            "name": "Mox",
            "kind": "digital",
            "mode": "manual",
            "url": "https://mox.com/"
        },
        {
            "name": "WeLab Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.welab.bank/en/"
        },
        {
            "name": "Airstar Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.airstarbank.com/en/"
        },
        {
            "name": "Ant Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.antbank.hk/en/"
        },
        {
            "name": "PAOb",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.paob.com.hk/en/"
        },
        {
            "name": "Fusion Bank",
            "kind": "digital",
            "mode": "manual",
            "url": "https://www.fusionbank.com/en/"
        },
        {
            "name": "Citi",
            "kind": "retail",
            "mode": "manual",
            "url": "https://www.citibank.com.hk/"
        },
        {
            "name": "Standard Chartered",
            "kind": "retail",
            "mode": "manual",
            "url": "https://www.sc.com/hk/"
        },
        {
            "name": "HSBC",
            "kind": "retail",
            "mode": "manual",
            "url": "https://www.hsbc.com.hk/"
        },
        {
            "name": "Hang Seng",
            "kind": "retail",
            "mode": "manual",
            "url": "https://www.hangseng.com/"
        },
        {
            "name": "BOCHK",
            "kind": "retail",
            "mode": "manual",
            "url": "https://www.bochk.com/"
        }
    ],
    "auto_pattern": "(\\d\\.\\d{1,2})\\s*(?:%|厘)"
}

# Starting values so the table renders on day one. Placeholders - edit
# data/rates_manual.json with the real promo rates.
DEFAULT_RATES = {
    "ZA Bank": 4.20, "livi Bank": 4.05, "Mox": 3.98, "WeLab Bank": 3.90,
    "Airstar Bank": 3.80, "Ant Bank": 3.72, "PAOb": 3.68, "Fusion Bank": 3.55,
    "Citi": 3.50, "Standard Chartered": 3.40, "HSBC": 3.20,
    "Hang Seng": 3.15, "BOCHK": 3.10,
}


def bootstrap():
    """Write index.html and the manual rates file if they do not exist yet."""
    (ROOT / "data").mkdir(exist_ok=True)
    page = ROOT / "index.html"
    if not page.exists() or page.read_text(encoding="utf-8") != INDEX_HTML:
        page.write_text(INDEX_HTML, encoding="utf-8")
        print("Wrote index.html")
    manual = ROOT / "data/rates_manual.json"
    if not manual.exists():
        manual.write_text(json.dumps(DEFAULT_RATES, indent=2), encoding="utf-8")
        print("Created data/rates_manual.json - fill in today's rates")


LOG = []


def log(msg):
    print(msg)
    LOG.append(msg)


def clean(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or ""))).strip()


def get_json(url, timeout=25):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "morning-brief/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        log(f"API failed {url}: {e}")
        return None


# ---------------------------------------------------------------- feeds

BROWSER_HEADERS = {
    # Several Hong Kong publishers reject requests that look like a bot or that
    # come from a datacentre IP with no browser headers. Ming Pao is one of them:
    # the feed URLs are correct, but a bare feedparser request gets nothing back.
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, text/xml, */*;q=0.8",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Connection": "close",
}


def fetch_feed(url, section, name):
    """Fetch a feed as a browser would. Returns bytes, or None after logging why."""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read()
        if not body:
            log(f"[{section}] {name}: empty response")
            return None
        return body
    except urllib.error.HTTPError as e:
        log(f"[{section}] {name}: HTTP {e.code} {e.reason}")
    except Exception as e:
        log(f"[{section}] {name}: {e}")
    return None


def entry_time(e):
    for key in ("published_parsed", "updated_parsed"):
        t = getattr(e, key, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def fetch_section(key, sec):
    """Collect, time-filter and keyword-filter one section's feeds."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CFG.get("window_hours", 26))
    inc = [w.lower() for w in sec.get("include", [])]
    exc = [w.lower() for w in sec.get("exclude", [])]
    items = []

    for feed in sec["feeds"]:
        raw = fetch_feed(feed["url"], key, feed["name"])
        if raw is None:
            continue
        parsed = feedparser.parse(raw)
        if not parsed.entries:
            log(f"[{key}] {feed['name']}: fetched but no entries parsed")
            continue

        for e in parsed.entries:
            when = entry_time(e)
            if when and when < cutoff:
                continue
            title = clean(getattr(e, "title", ""))
            summary = clean(getattr(e, "summary", ""))[:900]
            if not title:
                continue
            blob = (title + " " + summary).lower()

            # Back-test rule: service notices and statistical releases never travel.
            if any(w in blob for w in exc):
                continue
            if inc and not any(w in blob for w in inc):
                continue

            if " - " in title and "news.google.com" in feed["url"]:
                title, _, publisher = title.rpartition(" - ")
                name = publisher.strip() or feed["name"]
                if publisher and summary.endswith(publisher):
                    summary = summary[: -len(publisher)].strip()
            else:
                name = feed["name"]
            item = {
                "title": title,
                "source": name,
                "url": getattr(e, "link", ""),
                "published": when.astimezone(HK).strftime("%d %b %H:%M") if when else "",
                "snippet": summary,
            }
            if not any(similar(item["title"], x["title"]) > 0.9 for x in items):
                items.append(item)
        time.sleep(0.1)

    log(f"[{key}] {len(items)} items after filtering")
    return items


def similar(a, b):
    na = re.sub(r"[^\w\u4e00-\u9fff]+", "", (a or "").lower())
    nb = re.sub(r"[^\w\u4e00-\u9fff]+", "", (b or "").lower())
    return SequenceMatcher(None, na, nb).ratio()


def cluster(items, threshold=0.72):
    groups = []
    for it in items:
        for g in groups:
            if any(similar(it["title"], m["title"]) >= threshold for m in g):
                g.append(it)
                break
        else:
            groups.append([it])
    groups.sort(key=len, reverse=True)
    return groups


# ---------------------------------------------------------------- HKMA

def hkma_block():
    daily = (get_json(CFG["hkma"]["daily"])
             or get_json(CFG["hkma"]["daily"] + "?sortby=end_of_date&sortorder=desc"))
    out = {"available": False}
    if not daily:
        return out
    try:
        recs = daily["result"]["records"]
        latest = recs[0]
        bal = float(latest["closing_balance"])
        prev = float(recs[1]["closing_balance"]) if len(recs) > 1 else bal

        flat = 0
        for r in recs:
            if abs(float(r["closing_balance"]) - bal) < 1:
                flat += 1
            else:
                break

        out.update({
            "available": True,
            "as_of": latest.get("end_of_date", ""),
            "balance_hkdm": bal,
            "change": bal - prev,
            "flat_sessions": flat,
            "hibor_1m": latest.get("hibor_fixing_1m"),
            "hibor_on": latest.get("hibor_overnight"),
            "base_rate": latest.get("disc_win_base_rate"),
        })
    except Exception as e:
        log(f"HKMA parse failed: {e}")
    return out


def hkma_year_ends(years=11):
    """Year-end closing balance for the bar chart.

    The daily-figures endpoint ignores the date filter in some deployments and
    just returns the latest record, which silently produces a chart of eleven
    identical bars. So we sanity-check the result and drop it rather than show
    something wrong.
    """
    bars = []
    this_year = datetime.now(HK).year
    for y in range(this_year - years + 1, this_year + 1):
        url = (CFG["hkma"]["daily"] +
               f"?from={y}-12-01&to={y}-12-31&sortby=end_of_date&sortorder=desc&pagesize=1")
        d = get_json(url)
        try:
            rec = d["result"]["records"][0]
            bars.append({"year": y, "value": float(rec["closing_balance"]),
                         "date": rec.get("end_of_date", "")})
        except Exception:
            bars.append({"year": y, "value": None, "date": ""})
        time.sleep(0.2)

    dated = [b for b in bars if b["date"] and b["value"] is not None]
    if len(dated) < 2:
        log("HKMA year query returned no usable history - using daily snapshots instead.")
        return []
    distinct_years = {b["date"][:4] for b in dated}
    if len(distinct_years) < 2:
        log("HKMA year filter ignored - every year returned the same record. "
            "Dropping the year chart; building history from daily snapshots instead.")
        return []
    return bars


def history_bars():
    """Our own rolling record of the aggregate balance.

    Appended to on every run, so the chart fills in over time and does not
    depend on the API honouring a date filter.
    """
    path = ROOT / "data/history.json"
    try:
        hist = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        hist = []

    h = hkma_block()
    if h.get("available") and h.get("as_of"):
        if not any(x["date"] == h["as_of"] for x in hist):
            hist.append({"date": h["as_of"], "value": h["balance_hkdm"]})
    hist = sorted(hist, key=lambda x: x["date"])[-400:]
    path.write_text(json.dumps(hist, indent=2), encoding="utf-8")

    return [{"year": x["date"][5:10], "value": x["value"], "date": x["date"]}
            for x in hist[-30:]]


# ---------------------------------------------------------------- rates

def rate_table():
    banks = BANKS
    manual_path = ROOT / "data/rates_manual.json"
    manual = json.loads(manual_path.read_text(encoding="utf-8")) if manual_path.exists() else {}
    prev_path = ROOT / "data/rates_prev.json"
    prev = json.loads(prev_path.read_text(encoding="utf-8")) if prev_path.exists() else {}

    rows = []
    for b in banks["banks"]:
        rate = manual.get(b["name"])
        if b.get("mode") == "auto":
            log(f"auto mode not enabled for {b['name']}; using manual value")
        if rate is None:
            continue
        before = prev.get(b["name"])
        rows.append({
            "name": b["name"], "kind": b["kind"], "rate": float(rate),
            "change_bp": round((float(rate) - float(before)) * 100) if before is not None else None,
            "url": b.get("url", ""),
        })

    rows.sort(key=lambda r: r["rate"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    prev_path.write_text(json.dumps({r["name"]: r["rate"] for r in rows}, indent=2), encoding="utf-8")

    movers = [r for r in rows if r.get("change_bp")]
    movers.sort(key=lambda r: abs(r["change_bp"]), reverse=True)
    return {"tenor": banks["tenor"], "rows": rows, "movers": movers[:3]}


# ---------------------------------------------------------------- weather

def weather():
    d = get_json(CFG["weather"])
    try:
        f = d["weatherForecast"][0]
        return {
            "available": True,
            "desc": f.get("forecastWeather", ""),
            "tmin": f["forecastMintemp"]["value"], "tmax": f["forecastMaxtemp"]["value"],
            "hmin": f["forecastMinrh"]["value"], "hmax": f["forecastMaxrh"]["value"],
        }
    except Exception:
        return {"available": False}


# ---------------------------------------------------------------- model

PROMPT = """You are writing a personal morning brief for a Hong Kong banking professional.

Use ONLY the article metadata provided. Never state a fact that is not in it.
If a cluster has nothing but a headline, say so rather than inventing detail.

Sections and their rules:

work — 3 items max. For each, write `zh` as EXACTLY three short Traditional Chinese
  lines (Hong Kong written style), one fact per line, each under 30 characters.
  Also write `en`, a 2-4 sentence English summary.

smalltalk_hk, smalltalk_sg — for each item write `headline` (English is fine) and
  `body`, at most two sentences. No conversation scripts, no suggested openers.
  Just the story.

FILL EVERY SECTION. Each maximum is a target, not a ceiling to shy away from.
Return the maximum unless there genuinely are not that many distinct stories in
the material. A section with one item when twenty candidates were supplied is
wrong. If two stories are about different events, include both.

personal_hk — Traditional Chinese. `headline` is the story's own headline,
  `body` is AT MOST TWO short lines. Select for what people actually repeat:
  奇案/人情, 意外 with a specific cause, 藝人健康或離世, free or limited-run
  exhibitions and events with a date, and new policy that changes daily life.
  REJECT routine service notices, scheduled engineering work, and statistical
  releases with no person in them. Everything else is fair game: school
  incidents, court cases, accidents, celebrity news, exhibitions, food, sport,
  weather events, transport disruption that affects people, community stories.
  A headline-only item still counts if the headline is itself the story; set
  `body` to "" rather than dropping it.

personal_sg — English. Government, parties and ministers only. Same two-line cap.

Return ONLY a JSON object keyed by section name, each a list of objects with:
  zh (work only, array of exactly 3 strings)
  headline, body (non-work sections)
  en (work only)
  sources: array of {name, url}

CLUSTERS:
{payload}
"""


def gemini_models(key):
    """Ask Google which models this key can actually use for generateContent."""
    for ver in ("v1beta", "v1"):
        url = f"https://generativelanguage.googleapis.com/{ver}/models?pageSize=200"
        req = urllib.request.Request(url, headers={"x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:
            log(f"ListModels {ver} failed: {e}")
            continue
        names = [m["name"].split("/")[-1] for m in data.get("models", [])
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        if names:
            log(f"Models available ({ver}): {', '.join(names[:40])}")
            return ver, names
    return None, []


def rank_models(names):
    """Prefer free Flash text models, newest first. Skip image/audio variants."""
    def score(n):
        if any(x in n for x in ("image", "tts", "audio", "embedding", "live")):
            return (-1, 0)
        nums = re.findall(r"(\d+(?:\.\d+)?)", n)
        ver = float(nums[0]) if nums else 0.0
        tier = 3 if ("flash" in n and "lite" not in n) else 2 if "flash" in n else 1
        return (tier, ver)
    return sorted([n for n in names if score(n)[0] > 0], key=score, reverse=True)


def gemini(prompt):
    """Google AI Studio free tier. Discovers a working model rather than
    hardcoding a name, because Google retires model IDs frequently."""
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set")

    ver, available = gemini_models(key)
    if not available:
        raise RuntimeError("Could not list models - check the API key is valid")

    wanted = os.getenv("LLM_MODEL") or ""
    order = ([wanted] if wanted in available else []) + rank_models(available)
    if wanted and wanted not in available:
        log(f"LLM_MODEL '{wanted}' is not available to this key - ignoring it")

    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 32000,
            # Flash models spend output budget on internal reasoning first; with a
            # small cap the reply gets cut off mid-JSON, which is exactly what
            # happened here. Zero keeps the whole budget for the answer.
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }).encode("utf-8")

    last = None
    for model in order[:4]:
        url = (f"https://generativelanguage.googleapis.com/{ver}"
               f"/models/{model}:generateContent")
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = json.loads(r.read().decode("utf-8"))
            text = "".join(part.get("text", "")
                           for part in data["candidates"][0]["content"]["parts"])
            log(f"Model used: {model}")
            return text, model
        except Exception as e:
            log(f"Model {model} failed: {e}")
            last = e
    raise RuntimeError(f"All candidate models failed; last error: {last}")


def parse_json_loose(text):
    """Parse the model's reply, repairing a truncated tail if need be.

    A cut-off reply is still mostly useful - it is the last item that is
    incomplete, not the first eight. Walk back to the last complete object,
    close whatever brackets are still open, and keep what parsed.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        log(f"Model reply did not parse ({e}); attempting repair")

    # Candidate cut points: the end of every complete object, latest first.
    cuts = [m.end() for m in re.finditer(r"\}", text)]
    for cut in reversed(cuts):
        head = text[:cut]
        closing = ("]" * (head.count("[") - head.count("]"))
                   + "}" * (head.count("{") - head.count("}")))
        # try both orderings; nesting differs between a truncated list and dict
        for tail in (closing, closing[::-1]):
            try:
                data = json.loads(head + tail)
                log(f"Repaired reply, kept {cut:,} of {len(text):,} characters")
                return data
            except json.JSONDecodeError:
                continue
    raise ValueError("Could not repair the model reply")


def call_model(payload):
    provider = (os.getenv("LLM_PROVIDER") or "gemini").lower()
    prompt = PROMPT.replace("{payload}", json.dumps(payload, ensure_ascii=False))
    log(f"Prompt size: {len(prompt):,} characters, "
        f"{sum(len(v) for v in payload.values())} clusters")

    if provider == "gemini":
        text, model = gemini(prompt)
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
        return parse_json_loose(text), f"gemini:{model}"

    if provider == "anthropic":
        key = os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        from anthropic import Anthropic
        model = os.getenv("LLM_MODEL") or "claude-sonnet-4-6"
        r = Anthropic(api_key=key).messages.create(
            model=model, max_tokens=4000,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in r.content if b.type == "text")
    else:
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY not set")
        from openai import OpenAI
        model = os.getenv("LLM_MODEL") or "gpt-5-mini"
        r = OpenAI(api_key=key).responses.create(model=model, input=prompt)
        text = r.output_text
        model = f"openai:{model}"

    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.S)
    return parse_json_loose(text), (os.getenv("LLM_MODEL") or model)


def sentences(text, n=3, cap=34):
    """Split an RSS snippet into up to n short lines."""
    # Split on CJK full stops, and on Latin ones only when followed by a space,
    # so decimals like "3.5厘" and "0.3%" survive intact.
    parts = [p.strip() for p in
             re.split(r"(?<=[。！？])\s*|(?<=[.!?])\s+", text or "") if p and p.strip()]
    out = []
    for p in parts:
        while len(p) > cap and len(out) < n:
            cut = p.rfind("，", 0, cap) + 1 or p.rfind(",", 0, cap) + 1 or cap
            out.append(p[:cut].strip()); p = p[cut:].strip()
        if p and len(out) < n:
            out.append(p[:cap].strip())
        if len(out) >= n:
            break
    return out or [(text or "")[:cap]]


def redundant(title, body):
    """True when the snippet adds nothing beyond the headline."""
    norm = lambda t: re.sub(r"[^\w\u4e00-\u9fff]+", "", (t or "").lower())
    t, b = norm(title), norm(body)
    if not b:
        return True
    return b.startswith(t[:24]) or t.startswith(b[:24]) or similar(t, b) > 0.7


def rss_digest(collected):
    """No-model mode. Uses the publisher's own RSS summary, which for 明報 and
    HK01 is usually two or three usable sentences. Not as sharp as a model pass,
    but free, instant, and it never invents anything."""
    out = {}
    for key, groups in collected.items():
        sec = CFG["sections"][key]
        out[key] = []
        for g in groups[: sec["max_items"]]:
            lead = g[0]
            body = lead.get("snippet") or ""
            srcs = []
            seen = set()
            for m in g[:4]:
                if m["source"] in seen:
                    continue
                seen.add(m["source"])
                srcs.append({"name": m["source"], "url": m["url"]})
            thin = redundant(lead["title"], body)
            entry = {"sources": srcs}
            if key == "work":
                if thin:
                    entry["zh"] = [lead["title"][:34], "（只有標題，未有內文）", ""]
                    entry["en"] = "Headline only - this feed carried no article text."
                else:
                    lines = sentences(body, 3)
                    while len(lines) < 3:
                        lines.append("")
                    entry["zh"] = lines[:3]
                    entry["en"] = body[:600]
            else:
                entry["headline"] = lead["title"]
                entry["body"] = "" if thin else " ".join(sentences(body, 2, 60))
            out[key].append(entry)
    return out


# ---------------------------------------------------------------- main

def main():
    collected = {}
    payload = {}
    for key, sec in CFG["sections"].items():
        groups = cluster(fetch_section(key, sec))
        collected[key] = groups
        # Keep the prompt small. With 17 publishers the raw material is far more
        # than the model needs to choose from, and an oversized prompt just times
        # out - which is why this silently fell back to RSS.
        payload[key] = [
            [{"title": m["title"], "source": m["source"], "url": m["url"],
              "published": m["published"], "snippet": m["snippet"][:280]}
             for m in g[:3]]
            for g in groups[: min(sec["max_items"] * 5, 30)]
        ]

    try:
        sections, method = call_model(payload)
    except Exception as e:
        log(f"Model step skipped or failed ({e}) — using RSS summaries")
        sections, method = rss_digest(collected), "rss-only"

    now = datetime.now(HK)
    out = {
        "report_date": now.strftime("%A, %-d %B %Y") if os.name != "nt" else now.strftime("%A, %d %B %Y"),
        "generated_at": now.strftime("%d %b %Y %H:%M HKT"),
        "generated_iso": now.isoformat(),
        "build": {"method": method, "log": LOG},
        "weather": weather(),
        "hkma": hkma_block(),
        "hkma_bars": hkma_year_ends() or history_bars(),
        "rates": rate_table(),
        "labels": {k: v["label"] for k, v in CFG["sections"].items()},
        "sections": sections,
    }
    (ROOT / "data/brief.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote data/brief.json via {method}")




INDEX_HTML = r'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<title>Morning Brief</title>
<style>
  :root{
    --bg:#fbfaf9; --card:#fff; --ink:#1c1917; --ink2:#44403c; --muted:#78716c;
    --line:#e7e5e4; --hair:#f5f5f4; --zebra:#fafaf9;
    --shadow:0 1px 2px rgba(28,25,23,.05),0 6px 20px rgba(28,25,23,.045);
    --work:#1d4ed8; --work-bg:#eff6ff; --work-ink:#1e3a8a;
    --talk:#7c3aed; --talk-bg:#f5f3ff; --talk-ink:#5b21b6;
    --life:#b45309;
    --up:#047857; --down:#b91c1c; --bar:#1d4ed8; --warn-bg:#fef3c7; --warn-ink:#78350f; --warn-line:#fcd34d;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --bg:#0c0a09; --card:#1c1917; --ink:#fafaf9; --ink2:#d6d3d1; --muted:#a8a29e;
      --line:#292524; --hair:#232020; --zebra:#211e1c; --shadow:0 1px 2px rgba(0,0,0,.5);
      --work:#93c5fd; --work-bg:#172554; --work-ink:#bfdbfe;
      --talk:#c4b5fd; --talk-bg:#2e1065; --talk-ink:#ddd6fe;
      --life:#fcd34d;
      --up:#34d399; --down:#f87171; --bar:#60a5fa;
      --warn-bg:#451a03; --warn-ink:#fde68a; --warn-line:#78350f;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"PingFang HK","Noto Sans HK",Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased}
  .wrap{max-width:760px;margin:auto;padding:18px 16px 64px}
  .mono{font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
  .date{font-size:11.5px;font-weight:700;letter-spacing:.13em;text-transform:uppercase;color:var(--muted)}
  h1{margin:5px 0 3px;font-size:29px;line-height:1.1;letter-spacing:-.022em}
  .sub{color:var(--muted);font-size:13px}
  .stale{display:none;margin-top:14px;padding:12px 14px;border-radius:11px;
    background:var(--warn-bg);border:1px solid var(--warn-line);color:var(--warn-ink);
    font-size:13px;line-height:1.5}
  .stale.show{display:block}
  .wx{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-top:14px;padding:9px 13px;
    background:var(--card);border:1px solid var(--line);border-radius:11px;
    font-size:13px;color:var(--ink2);box-shadow:var(--shadow)}
  .wx b{color:var(--ink)}
  .panel{margin-top:16px;background:var(--card);border:1px solid var(--line);
    border-radius:14px;padding:15px 16px;box-shadow:var(--shadow)}
  .ptitle{font-size:14px;font-weight:680;margin:0 0 2px}
  .asof{font-size:11.5px;color:var(--muted);margin-bottom:12px}
  .big{display:flex;align-items:baseline;gap:10px;margin-bottom:3px}
  .bigval{font-size:27px;font-weight:720;letter-spacing:-.025em}
  .bigmeta{font-size:12.5px;color:var(--muted)}
  .up{color:var(--up)}.down{color:var(--down)}
  .bars{display:flex;align-items:flex-end;gap:4px;height:70px;margin-top:14px}
  .bcol{flex:1;display:flex;flex-direction:column;justify-content:flex-end;height:100%}
  .b{width:100%;background:var(--bar);opacity:.5;border-radius:2px 2px 0 0;min-height:2px}
  .b.hi{opacity:1}.b.lo{opacity:.22}.b.now{opacity:1;background:var(--ink)}
  .blab{display:flex;gap:4px;margin-top:5px}
  .blab span{flex:1;text-align:center;font-size:9.5px;color:var(--muted)}
  .notes{margin-top:11px;font-size:12.5px;color:var(--muted);line-height:1.55}
  .notes b{color:var(--ink);font-weight:650}
  table{width:100%;border-collapse:collapse;margin-top:4px;font-size:13.5px}
  th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--muted);font-weight:700;padding:0 0 7px}
  th.r,td.r{text-align:right}
  td{padding:6px 0;border-top:1px solid var(--hair)}
  tr:nth-child(even) td{background:var(--zebra)}
  td.rank{width:24px;color:var(--muted);font-size:11.5px}
  .bank{font-weight:600}
  .kind{font-size:10.5px;color:var(--muted);margin-left:6px;font-weight:400}
  .rate{font-weight:680}.chg{font-size:11.5px;width:48px}
  tr.cut td{border-top:1.5px dashed var(--line)}
  .cutlab{font-size:10.5px;color:var(--muted);padding-top:6px}
  .newpromo{margin-top:13px;border-top:1px solid var(--hair);padding-top:10px}
  .newpromo .h{font-size:10.5px;text-transform:uppercase;letter-spacing:.07em;
    color:var(--muted);font-weight:700;margin-bottom:6px}
  .np{font-size:13px;line-height:1.5;margin:5px 0;color:var(--ink2)}
  .np b{color:var(--ink)}
  .section{margin-top:32px}
  .shead{display:flex;align-items:baseline;gap:9px}
  .dot{width:8px;height:8px;border-radius:50%;flex:0 0 auto;position:relative;top:-1px}
  .section h2{font-size:19px;margin:0;letter-spacing:-.015em}
  .scount{margin-left:auto;font-size:12px;color:var(--muted)}
  .sub2{font-size:11.5px;font-weight:750;letter-spacing:.08em;text-transform:uppercase;
    color:var(--muted);margin:18px 0 7px}
  .wcard{background:var(--card);border:1px solid var(--line);border-radius:12px;
    padding:12px 14px;margin:8px 0;box-shadow:var(--shadow)}
  .wtop{display:flex;gap:7px;align-items:center;margin-bottom:6px;font-size:11px}
  .chip{font-weight:650;padding:2px 7px;border-radius:5px;background:var(--work-bg);color:var(--work-ink)}
  .wtop .src{margin-left:auto;color:var(--muted)}
  .zh3{font-size:14.5px;line-height:1.5;margin:0;color:var(--ink)}
  .zh3 span{display:block}
  details{margin-top:7px}
  summary{font-size:12px;color:var(--work);cursor:pointer;font-weight:600;
    list-style:none;display:inline-flex;align-items:center;gap:4px}
  summary::-webkit-details-marker{display:none}
  summary::before{content:"›";font-size:14px;transition:transform .15s}
  details[open] summary::before{transform:rotate(90deg)}
  .en{margin-top:8px;padding:10px 11px;background:var(--hair);border-radius:8px;
    font-size:13px;line-height:1.55;color:var(--ink2)}
  .en a{color:var(--work);text-decoration:none;font-weight:600}
  .card{background:var(--card);border:1px solid var(--line);border-radius:13px;
    padding:14px 15px;margin:8px 0;box-shadow:var(--shadow)}
  .headline{font-weight:680;font-size:15.5px;line-height:1.35;margin:0 0 5px;letter-spacing:-.01em}
  .two{font-size:14px;line-height:1.55;color:var(--ink2);margin:0}
  .srcs{margin-top:7px;font-size:11.5px;color:var(--muted)}
  .srcs a{color:var(--muted)}
  .empty{color:var(--muted);font-size:13px;padding:10px 0}
  footer{margin-top:26px;color:var(--muted);font-size:11.5px;line-height:1.6}
  @media(max-width:560px){h1{font-size:25px}.bars{height:58px}}
</style>
</head>
<body>
<main class="wrap">
  <div class="date" id="date">Loading…</div>
  <h1>Morning Brief</h1>
  <div class="sub" id="sub"></div>
  <div class="stale" id="stale"></div>
  <div id="wx"></div>
  <div id="panels"></div>
  <div id="sections"></div>
  <footer id="foot"></footer>
</main>

<script>
const esc = s => String(s ?? "").replace(/[&<>"']/g, m =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[m]));
const $ = id => document.getElementById(id);

function hkDay(d){
  return new Intl.DateTimeFormat("en-CA",{timeZone:"Asia/Hong_Kong",
    year:"numeric",month:"2-digit",day:"2-digit"}).format(d);
}

function weatherStrip(w){
  if(!w || !w.available) return "";
  return `<div class="wx"><b>${esc(w.desc)}</b>
    <span>${esc(w.tmin)}–${esc(w.tmax)}°C</span>
    <span>濕度 ${esc(w.hmin)}–${esc(w.hmax)}%</span></div>`;
}

function chgText(h){
  return h.change === 0 ? "<b>unchanged</b>"
    : `<b class="${h.change>0?'up':'down'}">${h.change>0?'+':''}$${(h.change/1000).toFixed(1)}bn</b>`;
}
function balancePanel(h, bars){
  if(!h || !h.available) return "";
  const bn = v => "$" + (v/1000).toFixed(1) + "bn";
  const vals = bars.filter(b => b.value != null);
  const max = Math.max(...vals.map(b => b.value), h.balance_hkdm);
  if (vals.length < 2) {
    return `<section class="panel">
      <div class="ptitle">Aggregate balance</div>
      <div class="asof">HKMA daily figures, ${esc(h.as_of)}.</div>
      <div class="big"><span class="bigval mono">${bn(h.balance_hkdm)}</span>
        <span class="bigmeta">vs yesterday ${chgText(h)}</span></div>
      <div class="bigmeta">1M HIBOR <b>${esc(h.hibor_1m ?? "n/a")}%</b> · overnight <b>${esc(h.hibor_on ?? "n/a")}%</b> · base rate <b>${esc(h.base_rate ?? "n/a")}%</b></div>
      <div class="notes">History is still building - the chart appears once a few days of figures have accumulated.</div>
    </section>`;
  }
  const peak = vals.reduce((a,b) => b.value > a.value ? b : a, vals[0]);
  const low  = vals.reduce((a,b) => b.value < a.value ? b : a, vals[0]);

  const cols = bars.map((b,i) => {
    const v = b.value ?? 0;
    const last = i === bars.length - 1;
    const cls = last ? "now" : (b === peak ? "hi" : (b === low ? "lo" : ""));
    return `<div class="bcol"><div class="b ${cls}" style="height:${(v/max*100).toFixed(1)}%"></div></div>`;
  }).join("");
  const labs = bars.map((b,i) =>
    `<span>${i === bars.length-1 ? "now" : String(b.year).slice(2)}</span>`).join("");

  const chg = h.change === 0 ? "<b>unchanged</b>"
    : `<b class="${h.change>0?'up':'down'}">${h.change>0?'+':''}${bn(h.change)}</b>`;

  return `<section class="panel">
    <div class="ptitle">Aggregate balance</div>
    <div class="asof">HKMA daily figures, ${esc(h.as_of)}. Bars are year-end closing balance.</div>
    <div class="big"><span class="bigval mono">${bn(h.balance_hkdm)}</span>
      <span class="bigmeta">vs yesterday ${chg}${h.flat_sessions>1?` · ${h.flat_sessions} sessions flat`:""}</span></div>
    <div class="bigmeta">1M HIBOR <b>${esc(h.hibor_1m ?? "n/a")}%</b> · overnight <b>${esc(h.hibor_on ?? "n/a")}%</b> · base rate <b>${esc(h.base_rate ?? "n/a")}%</b></div>
    <div class="bars">${cols}</div><div class="blab">${labs}</div>
    <div class="notes"><b>Peak</b> ${bn(peak.value)}, ${peak.year} · <b>Low</b> ${bn(low.value)}, ${low.year}<br>
      Today is ${(h.balance_hkdm/peak.value*100).toFixed(0)}% of the ${peak.year} peak.</div>
  </section>`;
}

function ratePanel(r){
  if(!r || !r.rows.length) return "";
  const rows = r.rows.map(x => {
    const c = x.change_bp;
    const chg = (c === null || c === undefined || c === 0) ? "—"
      : `<span class="${c>0?'up':'down'}">${c>0?'+':''}${c}</span>`;
    return `<tr class="${x.rank===11?'cut':''}">
      <td class="rank">${x.rank}</td>
      <td><span class="bank">${esc(x.name)}</span><span class="kind">${esc(x.kind)}</span></td>
      <td class="r rate">${x.rate.toFixed(2)}%</td><td class="r chg">${chg}</td></tr>`;
  }).join("");
  const movers = (r.movers||[]).map(m =>
    `<div class="np"><b>${esc(m.name)}</b> ${m.change_bp>0?'+':''}${m.change_bp}bp to ${m.rate.toFixed(2)}%, now rank ${m.rank}.</div>`).join("");
  return `<section class="panel">
    <div class="ptitle">HKD time deposit promos — ${esc(r.tenor)}</div>
    <div class="asof">${r.rows.length} banks tracked &middot; edit data/rates_manual.json</div>
    <table class="mono"><thead><tr><th></th><th>Bank</th><th class="r">Rate</th><th class="r">1d</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div class="cutlab">Dashed line = top 10 cut-off.</div>
    ${movers ? `<div class="newpromo"><div class="h">Moved today · 3 max</div>${movers}</div>` : ""}
  </section>`;
}

function srcLine(sources){
  if(!sources || !sources.length) return "";
  return `<div class="srcs">` + sources.map(s => s.url
    ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a>`
    : esc(s.name)).join(" · ") + `</div>`;
}

function workCard(it){
  const zh = (it.zh||[]).slice(0,3).map(l => `<span>${esc(l)}</span>`).join("");
  const src = (it.sources||[])[0] || {};
  return `<article class="wcard">
    <div class="wtop"><span class="chip">${esc(it.tag || "Work")}</span>
      <span class="src">${esc(src.name || "")}</span></div>
    <p class="zh3">${zh}</p>
    ${it.en ? `<details><summary>English summary &amp; source</summary>
      <div class="en">${esc(it.en)}${srcLine(it.sources)}</div></details>` : srcLine(it.sources)}
  </article>`;
}

function plainCard(it){
  return `<article class="card">
    <h3 class="headline">${esc(it.headline)}</h3>
    ${it.body ? `<p class="two">${esc(it.body)}</p>`
              : `<p class="two" style="opacity:.6">Headline only - open the source.</p>`}
    ${srcLine(it.sources)}</article>`;
}

function render(D){
  $("date").textContent = D.report_date || "";
  $("sub").textContent  = D.generated_at ? `Built ${D.generated_at}` : "";
  $("wx").innerHTML = weatherStrip(D.weather);
  $("panels").innerHTML = balancePanel(D.hkma, D.hkma_bars||[]) + ratePanel(D.rates);

  const S = D.sections || {}, L = D.labels || {};
  const block = (title, colour, groups) => {
    const total = groups.reduce((n,g) => n + (g.items||[]).length, 0);
    const body = groups.map(g => {
      if(!(g.items||[]).length) return "";
      return (g.sub ? `<div class="sub2">${esc(g.sub)}</div>` : "") +
        g.items.map(g.work ? workCard : plainCard).join("");
    }).join("") || `<div class="empty">Nothing met the bar today.</div>`;
    return `<section class="section">
      <div class="shead"><span class="dot" style="background:${colour}"></span>
        <h2>${esc(title)}</h2><span class="scount">${total} item${total===1?"":"s"}</span></div>
      ${body}</section>`;
  };

  $("sections").innerHTML =
    block("Work", "var(--work)", [{items:S.work||[], work:true}]) +
    block("Small Talk", "var(--talk)", [
      {sub:"Hong Kong", items:S.smalltalk_hk||[]},
      {sub:"Singapore", items:S.smalltalk_sg||[]}]) +
    block("Personal", "var(--life)", [
      {sub:"香港 · 民生", items:S.personal_hk||[]},
      {sub:"Singapore · Government", items:S.personal_sg||[]}]);

  // staleness + degraded build
  const msgs = [];
  if(D.generated_iso){
    const built = hkDay(new Date(D.generated_iso)), today = hkDay(new Date());
    if(built !== today){
      const days = Math.round((new Date(today) - new Date(built))/864e5);
      msgs.push(`Last built ${built}, ${days} day${days===1?"":"s"} ago. Check the Actions tab.`);
    }
  }
  if(D.build && D.build.method === "fallback"){
    msgs.push("Summarisation did not run. Cards below are headline-level only.");
  }
  if(msgs.length){ $("stale").innerHTML = msgs.join("<br>"); $("stale").classList.add("show"); }

  $("foot").textContent = "Items flagged headline-only have no retrieved body text. "
    + "Open the source before repeating anything that matters.";
}

fetch(`data/brief.json?ts=${Date.now()}`, {cache:"no-store"})
  .then(r => r.ok ? r.json() : Promise.reject(r.status))
  .then(render)
  .catch(e => {
    $("date").textContent = "";
    $("sub").textContent = "Could not load data/brief.json — run the workflow once.";
  });
</script>
</body>
</html>
'''


if __name__ == "__main__":
    bootstrap()
    main()
