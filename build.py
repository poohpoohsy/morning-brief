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

import os, re, json, html, time, hashlib, urllib.request, urllib.error, http.cookiejar
from datetime import datetime, timezone, timedelta
from difflib import SequenceMatcher
from pathlib import Path

import feedparser

ROOT = Path(__file__).resolve().parent
HK = timezone(timedelta(hours=8))
LOG = []

# Flattened once at import; every section is filtered against it.

CFG = {
    "window_hours": 50,
    "sections": {
        "work": {
            "label": "Work",
            "max_items": 40,
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
            "max_items": 40,
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
            "max_items": 40,
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
            "max_items": 40,
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
            "max_items": 40,
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
        },
        "juicy_hk": {
            "label": "Juicy · 香港",
            "max_items": 40,
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
                },
                {
                    "name": "熱話 GN",
                    "url": "https://news.google.com/rss/search?q=%E9%A6%99%E6%B8%AF+%E7%86%B1%E8%A9%B1+OR+%E7%B6%B2%E6%B0%91+OR+%E7%88%AD%E8%AD%B0+OR+%E8%A2%AB%E6%8D%95+OR+%E9%86%9C%E8%81%9E+when%3A3d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                },
                {
                    "name": "奇案 GN",
                    "url": "https://news.google.com/rss/search?q=%E9%A6%99%E6%B8%AF+%E6%B3%95%E5%BA%AD+OR+%E5%88%A4%E5%9B%9A+OR+%E8%B2%AA%E6%B1%A1+OR+%E8%A9%90%E9%A8%99+when%3A3d&hl=zh-HK&gl=HK&ceid=HK:zh-Hant"
                }
            ],
            "include": [],
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
        "juicy_sg": {
            "label": "Juicy · Singapore",
            "max_items": 40,
            "feeds": [
                {
                    "name": "The Independent SG",
                    "url": "https://theindependent.sg/feed/"
                },
                {
                    "name": "Mothership GN",
                    "url": "https://news.google.com/rss/search?q=site%3Amothership.sg+when%3A3d&hl=en-SG&gl=SG&ceid=SG:en"
                },
                {
                    "name": "SG news GN",
                    "url": "https://news.google.com/rss/search?q=Singapore+%28court+OR+probe+OR+fined+OR+viral+OR+resigns+OR+scandal%29+when%3A3d&hl=en-SG&gl=SG&ceid=SG:en"
                },
                {
                    "name": "SG politics GN",
                    "url": "https://news.google.com/rss/search?q=Singapore+%28parliament+OR+minister+OR+PAP+OR+MAS+OR+policy%29+when%3A3d&hl=en-SG&gl=SG&ceid=SG:en"
                },
                {
                    "name": "SG life GN",
                    "url": "https://news.google.com/rss/search?q=Singapore+%28HDB+OR+COE+OR+hawker+OR+MRT+OR+cost+of+living%29+when%3A3d&hl=en-SG&gl=SG&ceid=SG:en"
                }
            ],
            "include": [],
            "exclude": [
                "horoscope",
                "advertorial"
            ]
        }
    },
    "hkma": {
        "daily": "https://api.hkma.gov.hk/public/market-data-and-statistics/daily-monetary-statistics/daily-figures-interbank-liquidity",
        "hibor": "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily",
        "fx": "https://api.hkma.gov.hk/public/market-data-and-statistics/monthly-statistical-bulletin/er-ir/er-eeri-daily",
        "sofr": "https://markets.newyorkfed.org/api/rates/secured/sofrai/last/2.json",
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
    ],
    "prompt_budget_chars": 60000,
    "output_ceiling": 40,
    "global_exclude": {
        "_comment": "Applied to every section, on top of each section's own list.",
        "not_hong_kong": [
            "科創板",
            "滬市",
            "深市",
            "A股",
            "創業板",
            "北交所",
            "國產GPU",
            "四小龍",
            "十五五",
            "十四五",
            "工信部",
            "國務院",
            "發改委",
            "內地芯片",
            "晶片替代",
            "美股動向",
            "道指",
            "納指",
            "標普",
            "美債息",
            "聯儲",
            "華爾街",
            "A-share",
            "STAR Market",
            "Wall Street",
            "Nasdaq",
            "Dow Jones"
        ],
        "market_plumbing": [
            "夜期",
            "成交資料",
            "期指",
            "收市報告",
            "指數成分",
            "沽空",
            "窩輪",
            "牛熊證",
            "每日成交",
            "изменение",
            "盤路",
            "技術走勢"
        ],
        "site_boilerplate": [
            "現有會員",
            "訂戶",
            "登入",
            "訂閱",
            "會員專享",
            "立即註冊",
            "免費試閱",
            "Subscribe",
            "Sign in",
            "paywall"
        ],
        "recruitment": [
            "招聘",
            "職位空缺",
            "應徵",
            "聘請",
            "學年）",
            "行政主任",
            "合約教師",
            "Job vacancy",
            "recruitment",
            "apply now"
        ],
        "weather_notices": [
            "酷熱天氣警告",
            "寒冷天氣警告",
            "避暑中心",
            "避寒中心",
            "強烈季候風",
            "紫外線指數",
            "空氣質素健康指數"
        ],
        "official_platitudes": [
            "密切留意",
            "定必增撥",
            "會繼續關注",
            "表示歡迎",
            "冀港隊",
            "予以支持",
            "高度重視",
            "持續跟進",
            "適時檢視",
            "全力以赴"
        ],
        "sport_fixtures": [
            "亞運會",
            "世界盃",
            "友賽",
            "超級聯賽",
            "賽果",
            "開幕禮",
            "揭幕戰"
        ]
    }
}

# Flattened once; every section is filtered against it.
GLOBAL_EXCLUDE = [w for k, v in CFG.get("global_exclude", {}).items()
                  if k != "_comment" for w in v]

BANKS = {
    "tenor": "3-month, new money, HKD",
    "banks": [
        {
            "name": "ZA Bank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://za.group/en/bank"
        },
        {
            "name": "livi Bank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://www.livibank.com/en/"
        },
        {
            "name": "Mox",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://mox.com/"
        },
        {
            "name": "WeLab Bank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://www.welab.bank/en/"
        },
        {
            "name": "Airstar Bank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://www.airstarbank.com/en/"
        },
        {
            "name": "Ant Bank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://www.antbank.hk/en/"
        },
        {
            "name": "PAObank",
            "kind": "virtual",
            "mode": "manual",
            "url": "https://www.paob.com.hk/en/"
        },
        {
            "name": "Fusion Bank",
            "kind": "virtual",
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
    "Airstar Bank": 3.80, "Ant Bank": 3.72, "PAObank": 3.68, "Fusion Bank": 3.55,
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
            # Titles often carry a site name: "…搜查令|香港經濟日報". Strip it so
            # it neither clutters the card nor skews the duplicate check.
            title = re.split(r"\s*[|｜]\s*", title)[0].strip()
            blob = (title + " " + summary).lower()
            if any(w.lower() in blob for w in GLOBAL_EXCLUDE):
                continue

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


# ---------------------------------------------------------------- HKMA / treasury
#
# The public API is GET-only (a POST really is HTTP 405, from Kong). The 405s
# in the daily log are a different response: Aliyun's WAF, in front of that
# gateway, answers with an HTML block page and the reason "Not Allowed" when a
# burst of near-identical query strings looks hostile. Date windows also do
# nothing unless `choose` names the column (apidocs.hkma.gov.hk). Without it,
# every year-end call returned the same latest row, the chart was discarded,
# and the call that would have extended history.json was the one the WAF then
# blocked. One latest-page GET, with the gateway cookie and a short retry,
# replaces that burst.

LIQ_KEEP = (
    "end_of_date", "closing_balance", "opening_balance", "disc_win_base_rate",
    "hibor_overnight", "hibor_fixing_1m", "cu_weakside", "cu_strongside",
    "market_activities", "interest_payment", "discount_window_reversal",
    "discount_window_activities", "forex_trans_t1", "forex_trans_t2",
    "forex_trans_t3",
)
HIBOR_TENORS = (
    ("ON", "Overnight", "ir_overnight"),
    ("1W", "1-week", "ir_1w"),
    ("1M", "1-month", "ir_1m"),
    ("3M", "3-month", "ir_3m"),
    ("6M", "6-month", "ir_6m"),
    ("12M", "12-month", "ir_12m"),
)
BALANCE_PARTS = (
    ("market_activities", "Market activities"),
    ("interest_payment", "EFBN interest / issuance"),
    ("discount_window_reversal", "Discount-window reversal"),
    ("discount_window_activities", "Discount window"),
)
CHART_BARS = 36
_HKMA_OPENER = None
_WAF_NOTE = False
HKMA_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-HK,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Referer": "https://apidocs.hkma.gov.hk/",
    "Connection": "close",
}


def num(v):
    """Parse an HKMA number. Blanks and dashes stay missing — never zero."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "").replace("＋", "+").replace("－", "-")
    if not s or s in {"-", "+", "—", "–", "N/A", "n/a", "null", "None"}:
        return None
    try:
        return float(s.replace("+", ""))
    except ValueError:
        return None


def hkma_opener():
    global _HKMA_OPENER
    if _HKMA_OPENER is None:
        jar = http.cookiejar.CookieJar()
        _HKMA_OPENER = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
    return _HKMA_OPENER


def hkma_get(url, timeout=30, attempts=4):
    """GET an HKMA JSON document, retrying when the WAF returns its 405 page."""
    global _WAF_NOTE
    last = "no attempt"
    for i in range(attempts):
        req = urllib.request.Request(url, headers=HKMA_HEADERS)
        try:
            with hkma_opener().open(req, timeout=timeout) as r:
                raw = r.read()
            if not raw or raw[:1] not in (b"{", b"["):
                last = "non-JSON body"
            else:
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code} {e.reason}"
            try:
                e.read(80)
            except Exception:
                pass
            if e.code == 405 and not _WAF_NOTE:
                _WAF_NOTE = True
                log("HKMA returned HTTP 405 Not Allowed — Aliyun's block page, "
                    "not a rejected GET. Retrying with the gateway cookie.")
            if e.code not in (405, 408, 429, 500, 502, 503, 504):
                break
        except Exception as e:
            last = str(e)
        if i + 1 < attempts:
            time.sleep(1.2 * (i + 1))
    log(f"HKMA failed {url}: {last}")
    return None


def hkma_records(data):
    if not isinstance(data, dict):
        return []
    header = data.get("header") or {}
    if header.get("success") is False:
        log(f"HKMA error {header.get('err_code')}: {header.get('err_msg')}")
        return []
    recs = (data.get("result") or {}).get("records")
    return recs if isinstance(recs, list) else []


def _slim(recs, keys):
    out = []
    for rec in recs:
        if not isinstance(rec, dict):
            continue
        out.append({k: rec.get(k) for k in keys if k in rec})
    return out


def _latest_date(recs, field):
    dates = [r.get(field) for r in recs if r.get(field)]
    return max(dates) if dates else ""


def _recent_enough(recs, field):
    latest = _latest_date(recs, field)
    if not latest:
        return False
    cutoff = (datetime.now(HK).date() - timedelta(days=6)).isoformat()
    return latest >= cutoff


def fetch_liquidity():
    """Latest interbank-liquidity page.

    The bare URL already returns the newest ~100 business days, which is the
    whole gap in history.json. A dated query is only the fallback, and it
    names the column with `choose`, which the API requires.
    """
    recs = _slim(hkma_records(hkma_get(CFG["hkma"]["daily"])), LIQ_KEEP)
    if _recent_enough(recs, "end_of_date"):
        log(f"HKMA liquidity: {len(recs)} sessions through {_latest_date(recs, 'end_of_date')}")
        return recs
    log("HKMA latest page missing or not current; requesting a date window")
    today = datetime.now(HK).date()
    start = today - timedelta(days=150)
    url = (f"{CFG['hkma']['daily']}?choose=end_of_date&from={start.isoformat()}"
           f"&to={today.isoformat()}&pagesize=220&offset=0"
           f"&sortby=end_of_date&sortorder=desc&fields={','.join(LIQ_KEEP)}")
    ranged = _slim(hkma_records(hkma_get(url)), LIQ_KEEP)
    if _recent_enough(ranged, "end_of_date"):
        log(f"HKMA liquidity window: {len(ranged)} sessions through "
            f"{_latest_date(ranged, 'end_of_date')}")
        return ranged
    # Keep a real but ageing page rather than throwing the numbers away.
    return ranged or recs


def fetch_hibor():
    base = CFG["hkma"]["hibor"]
    urls = [
        base + "?segment=hibor.fixing&pagesize=6&offset=0&sortby=end_of_day&sortorder=desc",
        base + "?segment=hibor.fixing&pagesize=6&offset=0",
    ]
    keys = ("end_of_day",) + tuple(field for _, _, field in HIBOR_TENORS)
    best = []
    for url in urls:
        recs = _slim(hkma_records(hkma_get(url)), keys)
        if recs and _recent_enough(recs, "end_of_day"):
            log(f"HIBOR fixing: {len(recs)} sessions through {_latest_date(recs, 'end_of_day')}")
            return recs
        if recs:
            best = recs
            log(f"HIBOR fixing looked old ({_latest_date(recs, 'end_of_day')}); trying another query")
    return best


def fetch_fx():
    """HKMA's exchange-rate series, then the ECB reference rate if that series is behind.

    The monthly-bulletin daily rates were last published at end-October on the
    14 Nov check, which is too old to place the spot in the band. Frankfurter
    republishes the ECB reference rate with no key.
    """
    base = CFG["hkma"]["fx"]
    urls = [
        base + "?fields=end_of_day,usd&pagesize=5&offset=0&sortby=end_of_day&sortorder=desc",
        base + "?pagesize=5&offset=0",
    ]
    best = []
    for url in urls:
        recs = _slim(hkma_records(hkma_get(url)), ("end_of_day", "usd"))
        priced = [r for r in recs if num(r.get("usd")) is not None]
        for row in priced:
            row["vendor"] = "HKMA"
        if priced and _recent_enough(priced, "end_of_day"):
            log(f"USD/HKD: HKMA through {_latest_date(priced, 'end_of_day')}")
            return priced
        if priced:
            best = priced
    ecb = fetch_ecb_fx()
    if _recent_enough(ecb, "end_of_day"):
        log(f"USD/HKD: HKMA series ends {_latest_date(best, 'end_of_day') or 'n/a'}; "
            f"using the ECB reference rate through {_latest_date(ecb, 'end_of_day')}")
        return ecb
    return best or ecb


def fetch_ecb_fx():
    end = datetime.now(HK).date()
    start = end - timedelta(days=14)
    url = f"https://api.frankfurter.app/{start.isoformat()}..{end.isoformat()}?from=USD&to=HKD"
    data = get_json(url)
    rates = data.get("rates") if isinstance(data, dict) else None
    if not isinstance(rates, dict):
        data = get_json("https://api.frankfurter.app/latest?from=USD&to=HKD")
        if not isinstance(data, dict) or "HKD" not in (data.get("rates") or {}):
            return []
        return [{"end_of_day": data.get("date"), "usd": data["rates"]["HKD"], "vendor": "ECB"}]
    rows = []
    for day, quote in rates.items():
        if isinstance(quote, dict) and num(quote.get("HKD")) is not None:
            rows.append({"end_of_day": day, "usd": quote["HKD"], "vendor": "ECB"})
    return rows


def fetch_sofr():
    """New York Fed 30-day compounded SOFR average. No key. Not CME Term SOFR."""
    data = get_json(CFG["hkma"]["sofr"])
    rows = _sofr_rows(data)
    if rows:
        return rows
    data = get_json("https://markets.newyorkfed.org/api/rates/all/latest.json")
    return _sofr_rows(data)


def _sofr_rows(data):
    if not isinstance(data, dict):
        return []
    out = []
    for row in data.get("refRates") or []:
        if not isinstance(row, dict) or row.get("average30day") is None:
            continue
        if row.get("type") not in (None, "", "SOFRAI"):
            continue
        out.append({"date": row.get("effectiveDate"),
                    "average30day": float(row["average30day"])})
    out.sort(key=lambda r: r.get("date") or "")
    return out


def load_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def load_history():
    hist = load_json(ROOT / "data/history.json", [])
    if not isinstance(hist, list):
        return []
    out = []
    for row in hist:
        if isinstance(row, dict) and row.get("date") and num(row.get("value")) is not None:
            out.append({"date": row["date"], "value": float(row["value"])})
    return out


def merge_history(points):
    """Fold API sessions into data/history.json. A failed fetch does not write."""
    hist = load_history()
    if not points:
        return hist
    by = {row["date"]: row for row in hist}
    added = 0
    changed = False
    for point in points:
        new = {"date": point["date"], "value": float(point["value"])}
        old = by.get(point["date"])
        if old is None:
            added += 1
            changed = True
        elif old["value"] != new["value"]:
            changed = True
        by[point["date"]] = new
    out = sorted(by.values(), key=lambda row: row["date"])[-400:]
    if changed:
        (ROOT / "data/history.json").write_text(
            json.dumps(out, indent=2) + "\n", encoding="utf-8")
        log(f"HKMA history: backfilled {added} sessions, {len(out)} stored, "
            f"latest {out[-1]['date']}")
    else:
        log(f"HKMA history: already current through {out[-1]['date'] if out else 'n/a'}")
    return out


def cache_path():
    return ROOT / "data/hkma_cache.json"


def load_cache():
    data = load_json(cache_path(), {})
    return data if isinstance(data, dict) else {}


def save_cache(cache):
    cache_path().write_text(
        json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def previous_headline():
    """Single snapshot from the last brief, used only when nothing newer loads."""
    prev = load_json(ROOT / "data/brief.json", {})
    if not isinstance(prev, dict):
        return None
    block = prev.get("hkma") or {}
    balance = ((prev.get("treasury") or {}).get("balance") or {})
    if block.get("available") and block.get("as_of") and num(block.get("balance_hkdm")) is not None:
        return {
            "record": {
                "end_of_date": block["as_of"],
                "closing_balance": block["balance_hkdm"],
                "disc_win_base_rate": block.get("base_rate"),
                "hibor_overnight": block.get("hibor_on"),
                "hibor_fixing_1m": block.get("hibor_1m"),
            },
            "change": block.get("change"),
            "flat_sessions": block.get("flat_sessions"),
        }
    if balance.get("available") and balance.get("as_of") and num(balance.get("value_hkdm")) is not None:
        return {
            "record": {
                "end_of_date": balance["as_of"],
                "closing_balance": balance["value_hkdm"],
                "disc_win_base_rate": balance.get("base_rate"),
            },
            "change": balance.get("change_hkdm"),
            "flat_sessions": balance.get("flat_sessions"),
        }
    return None


def _bp(latest, previous):
    if latest is None or previous is None:
        return None
    return round((latest - previous) * 100, 1)


def _sorted(recs, field):
    return sorted(recs, key=lambda r: r.get(field) or "")


def balance_view(recs, stale, carried=None):
    rows = _sorted([r for r in recs if r.get("end_of_date")], "end_of_date")
    if not rows:
        return {"available": False, "stale": False}
    latest = rows[-1]
    prev = rows[-2] if len(rows) > 1 else None
    value = num(latest.get("closing_balance"))
    if value is None:
        return {"available": False, "stale": False}
    if carried is not None:
        change = num(carried.get("change")) if carried.get("change") is not None else None
        # A stored 0 is a real unchanged day; only a missing field is unknown.
        if "change" in carried and carried.get("change") is not None:
            change = num(carried.get("change"))
        flat = carried.get("flat_sessions") or 1
    else:
        previous = num(prev.get("closing_balance")) if prev else None
        change = None if previous is None else value - previous
        flat = 0
        for row in reversed(rows):
            current = num(row.get("closing_balance"))
            if current is None or abs(current - value) >= 1:
                break
            flat += 1
    base = num(latest.get("disc_win_base_rate"))
    prev_base = num(prev.get("disc_win_base_rate")) if prev else None
    parts = []
    for key, label in BALANCE_PARTS:
        part = num(latest.get(key))
        if part is not None and abs(part) >= 1:
            parts.append({"label": label, "hkdm": part})
    return {
        "available": True,
        "stale": stale,
        "as_of": latest.get("end_of_date"),
        "value_hkdm": value,
        "change_hkdm": change,
        "flat_sessions": flat,
        "base_rate": base,
        "base_rate_change_bp": _bp(base, prev_base),
        "components": parts,
        "source": "HKMA daily figures of interbank liquidity",
    }


def hibor_view(recs, stale):
    rows = _sorted([r for r in recs if r.get("end_of_day")], "end_of_day")
    if len(rows) < 1:
        return {"available": False, "stale": False, "tenors": []}
    latest, prev = rows[-1], rows[-2] if len(rows) > 1 else None
    tenors = []
    for code, label, field in HIBOR_TENORS:
        rate = num(latest.get(field))
        previous = num(prev.get(field)) if prev else None
        tenors.append({
            "code": code, "label": label, "rate": rate,
            "change_bp": _bp(rate, previous),
        })
    if not any(t["rate"] is not None for t in tenors):
        return {"available": False, "stale": False, "tenors": []}
    return {
        "available": True,
        "stale": stale,
        "partial": False,
        "as_of": latest.get("end_of_day"),
        "prev_date": prev.get("end_of_day") if prev else None,
        "tenors": tenors,
        "source": "HKMA, HKAB HIBOR fixing",
    }


def hibor_from_liquidity(recs, stale):
    """Overnight and 1-month only, when the fixing endpoint did not answer."""
    rows = _sorted([r for r in recs if r.get("end_of_date")], "end_of_date")
    if not rows:
        return {"available": False, "stale": False, "tenors": []}
    latest, prev = rows[-1], rows[-2] if len(rows) > 1 else None
    mapping = {"ON": "hibor_overnight", "1M": "hibor_fixing_1m"}
    tenors = []
    for code, label, _field in HIBOR_TENORS:
        field = mapping.get(code)
        rate = num(latest.get(field)) if field else None
        previous = num(prev.get(field)) if field and prev else None
        tenors.append({
            "code": code, "label": label, "rate": rate,
            "change_bp": _bp(rate, previous),
        })
    if not any(t["rate"] is not None for t in tenors):
        return {"available": False, "stale": False, "tenors": []}
    return {
        "available": True,
        "stale": stale,
        "partial": True,
        "as_of": latest.get("end_of_date"),
        "prev_date": prev.get("end_of_date") if prev else None,
        "tenors": tenors,
        "source": "HKMA daily interbank liquidity (overnight and 1-month only)",
    }


def fx_view(recs, liquidity, stale):
    rows = _sorted([r for r in recs if r.get("end_of_day") and num(r.get("usd")) is not None],
                   "end_of_day")
    liq = _sorted([r for r in liquidity if r.get("end_of_date")], "end_of_date")
    latest_liq = liq[-1] if liq else {}
    strong = num(latest_liq.get("cu_strongside")) or 7.75
    weak = num(latest_liq.get("cu_weakside")) or 7.85
    flows = []
    for row in reversed(liq[-10:]):
        amount = num(row.get("market_activities"))
        if amount is not None and abs(amount) >= 1:
            flows.append({"date": row.get("end_of_date"), "hkdm": amount})
    forecast = []
    for key, when in (("forex_trans_t1", "T+1"), ("forex_trans_t2", "T+2"),
                      ("forex_trans_t3", "T+3")):
        amount = num(latest_liq.get(key))
        if amount is not None and abs(amount) >= 1:
            forecast.append({"when": when, "hkdm": amount})
    spot = num(rows[-1].get("usd")) if rows else None
    prev_spot = num(rows[-2].get("usd")) if len(rows) > 1 else None
    width = weak - strong
    aged = bool(rows) and not _recent_enough(rows, "end_of_day")
    vendor = (rows[-1].get("vendor") if rows else "") or ""
    source = ("ECB reference rate via Frankfurter, HKD per US dollar"
              if vendor == "ECB"
              else "HKMA daily exchange rates, HKD per US dollar")
    if spot is None or width == 0:
        return {
            "available": False, "stale": stale or aged, "strong": strong, "weak": weak,
            "market_activities": flows, "fx_forecast": forecast,
            "sessions_checked": min(10, len(liq)), "source": source,
        }
    spot = round(spot, 4)
    return {
        "available": True,
        "stale": stale or aged,
        "as_of": rows[-1].get("end_of_day"),
        "prev_date": rows[-2].get("end_of_day") if len(rows) > 1 else None,
        "spot": spot,
        "change_pips": None if prev_spot is None else round((spot - prev_spot) * 10000),
        "strong": strong,
        "weak": weak,
        "pct_through_band": (spot - strong) / width * 100,
        "pips_to_weak": round((weak - spot) * 10000),
        "pips_to_strong": round((spot - strong) * 10000),
        "market_activities": flows,
        "fx_forecast": forecast,
        "sessions_checked": min(10, len(liq)),
        "source": source,
    }


def overlay_hibor(hibor, liquidity, liq_stale):
    """Use the daily liquidity release for overnight and 1-month when it is newer.

    The HKAB fixing series in the monthly bulletin was only up to 30 Oct on the
    14 Nov run. Overnight and the 1-month fixing are also on the daily file.
    """
    rows = _sorted([r for r in liquidity if r.get("end_of_date")], "end_of_date")
    if not rows:
        if hibor.get("available") and hibor.get("as_of") and not _recent_enough(
                [{"end_of_day": hibor["as_of"]}], "end_of_day"):
            hibor["stale"] = True
        return hibor
    latest, prev = rows[-1], rows[-2] if len(rows) > 1 else None
    daily_as_of = latest.get("end_of_date") or ""
    curve_as_of = hibor.get("as_of") or ""
    newer = (not hibor.get("available")) or (daily_as_of > curve_as_of)
    if not newer:
        return hibor
    mapping = {"ON": "hibor_overnight", "1M": "hibor_fixing_1m"}
    if not hibor.get("available"):
        view = hibor_from_liquidity(liquidity, liq_stale)
        return view
    tenors = []
    replaced = False
    for tenor in hibor.get("tenors") or []:
        field = mapping.get(tenor["code"])
        rate = num(latest.get(field)) if field else None
        if rate is None:
            tenors.append(dict(tenor, as_of=curve_as_of))
            continue
        previous = num(prev.get(field)) if prev else None
        tenors.append({
            "code": tenor["code"], "label": tenor["label"], "rate": rate,
            "change_bp": _bp(rate, previous), "as_of": daily_as_of,
        })
        replaced = True
    if not replaced:
        return hibor
    hibor = dict(hibor)
    hibor["tenors"] = tenors
    hibor["mixed_dates"] = curve_as_of and curve_as_of != daily_as_of
    hibor["daily_as_of"] = daily_as_of
    hibor["curve_as_of"] = curve_as_of
    hibor["stale"] = False
    return hibor


def spread_view(hibor, sofr_rows, sofr_stale):
    tenor = next((t for t in (hibor.get("tenors") or []) if t.get("code") == "1M"), None)
    hibor_1m = tenor.get("rate") if tenor else None
    sofr = sofr_rows[-1] if sofr_rows else None
    usd = sofr.get("average30day") if sofr else None
    if hibor_1m is None or usd is None:
        return {
            "available": False,
            "stale": sofr_stale,
            "label": "1M HIBOR − 30-day average SOFR",
            "note": "Needs both a 1-month HIBOR fixing and the New York Fed 30-day SOFR average.",
        }
    return {
        "available": True,
        "stale": bool(sofr_stale or hibor.get("stale")),
        "label": "1M HIBOR − 30-day average SOFR",
        "hibor_1m": hibor_1m,
        "hibor_as_of": tenor.get("as_of") or hibor.get("as_of"),
        "usd_rate": usd,
        "usd_label": "30-day average SOFR",
        "usd_as_of": sofr.get("date"),
        "spread_bp": round((hibor_1m - usd) * 100, 1),
        "note": "US leg is the New York Fed 30-day compounded SOFR average, not CME Term SOFR.",
        "source": "HKMA; Federal Reserve Bank of New York",
    }


def bars_from(hist):
    return [{"year": row["date"][5:10], "value": row["value"], "date": row["date"]}
            for row in hist[-CHART_BARS:]]


def build_market():
    """Liquidity, HIBOR, USD/HKD and the SOFR spread. One pass, then the chart."""
    cache = load_cache()
    fresh = {}

    sofr = fetch_sofr()
    time.sleep(0.6)
    liquidity = fetch_liquidity()
    time.sleep(0.6)
    hibor_rows = fetch_hibor()
    time.sleep(0.6)
    fx_rows = fetch_fx()

    def keep(key, rows):
        if rows:
            fresh[key] = rows
            cache[key] = rows
            return rows, False
        saved = cache.get(key) or []
        if saved:
            log(f"{key}: showing the last good values; this run's call failed")
            return saved, True
        return [], False

    sofr_rows, sofr_stale = keep("sofr", sofr)
    liquidity, liq_stale = keep("liquidity", liquidity)
    hibor_rows, hibor_stale = keep("hibor", hibor_rows)
    fx_rows, fx_stale = keep("fx", fx_rows)
    if fresh:
        save_cache(cache)

    carried = None
    if not liquidity:
        headline = previous_headline()
        if headline:
            liquidity = [headline["record"]]
            carried = headline
            liq_stale = True
            log(f"HKMA liquidity: no series loaded; keeping the {headline['record']['end_of_date']} "
                "figure from the previous brief and marking it stale")

    if liquidity and carried is None:
        points = [{"date": r["end_of_date"], "value": num(r["closing_balance"])}
                  for r in liquidity
                  if r.get("end_of_date") and num(r.get("closing_balance")) is not None]
        hist = merge_history(points)
    else:
        hist = load_history()

    balance = balance_view(liquidity, liq_stale, carried)
    if hist:
        window = hist[-CHART_BARS:]
        balance["history_through"] = hist[-1]["date"]
        balance["window_change_hkdm"] = (
            window[-1]["value"] - window[0]["value"] if len(window) >= 2 else None)
        if balance.get("as_of") and hist[-1]["date"] < balance["as_of"]:
            balance["history_behind"] = True
    hibor = hibor_view(hibor_rows, hibor_stale)
    if not hibor.get("available"):
        hibor = hibor_from_liquidity(liquidity, liq_stale or hibor_stale)
    else:
        hibor = overlay_hibor(hibor, liquidity if carried is None else [], hibor_stale)
    fx = fx_view(fx_rows, liquidity if carried is None else [], fx_stale)
    # A one-row fallback has no market-activity history. Still show the band
    # levels from that row when the FX print itself loaded.
    if carried is not None and liquidity:
        lone = liquidity[-1]
        if num(lone.get("cu_strongside")):
            fx["strong"] = num(lone.get("cu_strongside"))
        if num(lone.get("cu_weakside")):
            fx["weak"] = num(lone.get("cu_weakside"))
    spread = spread_view(hibor, sofr_rows, sofr_stale)

    legacy = {
        "available": bool(balance.get("available")),
        "stale": bool(balance.get("stale")),
        "as_of": balance.get("as_of") or "",
        "balance_hkdm": balance.get("value_hkdm"),
        "change": balance.get("change_hkdm"),
        "flat_sessions": balance.get("flat_sessions") or 0,
        "hibor_1m": next((t["rate"] for t in hibor.get("tenors") or []
                          if t["code"] == "1M"), None),
        "hibor_on": next((t["rate"] for t in hibor.get("tenors") or []
                          if t["code"] == "ON"), None),
        "base_rate": balance.get("base_rate"),
    }
    treasury = {
        "balance": balance,
        "hibor": hibor,
        "fx": fx,
        "spread": spread,
    }
    return {"hkma": legacy, "bars": bars_from(hist), "treasury": treasury}


# ---------------------------------------------------------------- rates

def rate_table():
    """Build the promo rate table.

    Values come from data/rates_manual.json. Anything missing or null falls back
    to a placeholder so the table still renders - a blank panel just looks
    broken. Placeholders are flagged on the page so they are never mistaken for
    today's real rates.
    """
    manual_path = ROOT / "data/rates_manual.json"
    try:
        manual = json.loads(manual_path.read_text(encoding="utf-8"))
    except Exception:
        manual = {}

    prev_path = ROOT / "data/rates_prev.json"
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except Exception:
        prev = {}

    rows, placeholders = [], 0
    for b in BANKS["banks"]:
        value = manual.get(b["name"])
        is_placeholder = False
        if value is None:
            value = DEFAULT_RATES.get(b["name"])
            is_placeholder = value is not None
        if value is None:
            continue
        if is_placeholder:
            placeholders += 1
        before = prev.get(b["name"])
        if before is None and b["name"] == "PAObank":
            before = prev.get("PAOb")
        rows.append({
            "name": b["name"], "kind": b["kind"], "rate": float(value),
            "change_bp": (round((float(value) - float(before)) * 100)
                          if before is not None else None),
            "placeholder": is_placeholder,
            "url": b.get("url", ""),
        })

    rows.sort(key=lambda r: r["rate"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["rank"] = i

    prev_path.write_text(json.dumps({r["name"]: r["rate"] for r in rows}, indent=2),
                         encoding="utf-8")

    if placeholders:
        log(f"{placeholders} of {len(rows)} rates are placeholders - "
            f"edit data/rates_manual.json")

    movers = [r for r in rows if r.get("change_bp")]
    movers.sort(key=lambda r: abs(r["change_bp"]), reverse=True)
    return {"tenor": BANKS["tenor"], "rows": rows, "movers": movers[:3],
            "placeholders": placeholders}


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

THERE IS NO FIXED NUMBER OF ITEMS. Include every distinct story that belongs in
a section. Do not ration yourself: if forty candidates were supplied and thirty
are distinct and relevant, return thirty. Merge only genuine duplicates of the
same event. A section with three items when thirty candidates were supplied is
wrong. Keep each item short so that a long list stays readable.

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

juicy_hk (Traditional Chinese) and juicy_sg (English) — the stories people will
actually repeat this week. Rank and select as follows, in this order:

  1. MONEY PLUS A HUMAN FAULT ranks highest. A dispute over a lottery win, a
     bribe, a betrayal between colleagues, a fraud. These get repeated more than
     anything else.
  2. MERGE STORIES THAT SHARE A CAUSE into one item. Three separate construction
     accidents in one week are one story about site safety and oversight - write
     it as one item naming all three, not three items.
  3. KEEP LIGHT CONSUMER STORIES. A chain changing its seating rules, a decades-old
     shop closing, a restaurant opening. These are meal-table material and cost
     nobody anything to discuss.
  4. KEEP PRACTICAL ITEMS that carry a date or a number - a licensing timeline,
     a bond issue size, a fee change.
  5. DROP pure政治立場 commentary, sports results, and anything with no person in it.
  6. DROP anything without a Hong Kong angle. Mainland A-share listings, PRC
     five-year-plan policy and US market commentary do not belong here unless a
     Hong Kong company, regulator or listing is directly involved.
  7. DROP market plumbing (index data, futures turnover, technical charts),
     recruitment notices, site boilerplate, and official statements that contain
     no new fact - "會繼續關注", "定必增撥資源" and similar.

  Each item also needs a `tag` - one of: 奇案人情 / 醜聞 / 行業線 / 輕鬆 / 實用 / 敏感
  (or in English: scandal, human interest, industry, light, practical, sensitive).

  And a `raise` field, true or false. Set it to FALSE for anything where the
  other person's answer would expose a political position - national security
  cases, sentencing of activists, sovereignty questions, elections. These items
  still belong in the brief, because being uninformed is worse, but they are for
  knowing and not for raising. Everything else is true.


For juicy_hk and juicy_sg use `headline`, `body` (at most two sentences),
`tag` and `raise`.

talking_points — an object with exactly three keys: ceo, business, treasury.
Each value is a list of AT MOST 3 items. Use an empty list when the supplied
articles do not support that audience. Never add a fourth bullet, and never
write a bullet that is not tied to a supplied article.

  ceo — strategy, regulation, competition, virtual banks, HKMA, SFC,
    stablecoins and digital assets.
  business — product, customer and market moves by competitors.
  treasury — rate moves, liquidity, deposit competition and promo trends.

  Each item:
    point — one sentence. Only facts present in the supplied metadata.
    so_what — ONE line on what that fact means for a Hong Kong digital bank.
      An implication of the supplied fact, not a new fact. Do not introduce a
      number, name, date or market move that is not in the metadata.
    sources — one or more objects with name and url, copied from the supplied
      items. The url must appear in the payload. A bullet with no such url is
      useless and will be dropped.

  If you only have a headline, set point to that headline and so_what to "".
  Do not dress a headline up as a fuller story.

Return ONLY a JSON object.
Every news section is a list of objects with:
  zh (work only, array of exactly 3 strings)
  headline, body (non-work sections)
  en (work only)
  tag, raise (juicy sections only)
  sources: array of objects with name and url
Also include talking_points, shaped exactly as specified above.

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


def fit_budget(payload):
    """Trim the payload to the prompt budget, fairly rather than by section.

    Removes from whichever section currently has the most candidates, so a
    section with three stories keeps all three while one with eighty gives some
    back. Only bites on genuinely huge days.
    """
    budget = CFG.get("prompt_budget_chars", 60000)
    size = lambda p: len(json.dumps(p, ensure_ascii=False))
    dropped = 0
    while size(payload) > budget:
        biggest = max(payload, key=lambda k: len(payload[k]))
        if len(payload[biggest]) <= 1:
            break
        payload[biggest].pop()
        dropped += 1
    if dropped:
        log(f"Trimmed {dropped} clusters to fit the {budget:,} character budget")
    return payload


def render_prompt(payload, skip_talking=False, muted_keys=()):
    """Build the model prompt. Muted stories are already absent from payload."""
    prompt = PROMPT
    if skip_talking:
        start = "talking_points — an object with exactly three keys:"
        end = "Return ONLY a JSON object."
        if start in prompt and end in prompt:
            pre, rest = prompt.split(start, 1)
            _, post = rest.split(end, 1)
            prompt = (pre + "talking_points — omit this key entirely. The section is muted.\n\n"
                      + end + post)
        prompt = prompt.replace(
            "Also include talking_points, shaped exactly as specified above.\n",
            "Do not include a talking_points key.\n",
        )
    notes = []
    if muted_keys:
        notes.append("Do not write these muted sections: " + ", ".join(muted_keys) + ".")
    if skip_talking:
        notes.append("Do not write talking_points.")
    if notes:
        prompt = prompt.replace(
            "CLUSTERS:\n{payload}",
            " ".join(notes) + "\n\nCLUSTERS:\n{payload}",
        )
    return prompt.replace("{payload}", json.dumps(payload, ensure_ascii=False))


def call_model(payload, skip_talking=False, muted_keys=()):
    provider = (os.getenv("LLM_PROVIDER") or "gemini").lower()
    prompt = render_prompt(payload, skip_talking=skip_talking, muted_keys=muted_keys)
    log("Candidates sent: " + ", ".join(
        f"{k}={len(v)}" for k, v in payload.items()))
    log(f"Prompt size: {len(prompt):,} characters")

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


def rss_digest(collected, depth=1):
    """No-model mode. Uses the publisher's own RSS summary, which for 明報 and
    HK01 is usually two or three usable sentences. Not as sharp as a model pass,
    but free, instant, and it never invents anything."""
    out = {}
    for key, groups in collected.items():
        sec = CFG["sections"][key]
        out[key] = []
        for g in groups[: sec["max_items"] * depth]:
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
            entry = {"sources": srcs, "title": lead["title"]}
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

def top_up(sections, collected):
    """Fill out any section the model returned short.

    The model is conservative: given thirty candidates and a cap of eight it
    will often return three. Rather than lose good stories, take the clusters it
    passed over and add them in RSS form until the section reaches its quota.
    """
    rss = rss_digest(collected, depth=4)
    for key, sec in CFG["sections"].items():
        have = sections.get(key) or []
        # Fill to the number of distinct stories available, not a fixed number.
        want = min(len(collected.get(key) or []),
                   sec.get("max_items", 40),
                   CFG.get("output_ceiling", 40))
        if len(have) >= want:
            continue

        chosen = [(h.get("headline") or " ".join(h.get("zh") or [])) for h in have]
        added = 0
        for cand in rss.get(key, []):
            if len(have) >= want:
                break
            label = cand.get("headline") or " ".join(cand.get("zh") or [])
            # Chinese headlines share common phrases, so only drop a candidate
            # when it is close to a straight duplicate.
            if any(similar(label, c) > 0.75 for c in chosen):
                continue
            have.append(cand)
            chosen.append(label)
            added += 1
        if added:
            log(f"[{key}] model returned {len(have) - added}, topped up by {added}")
        sections[key] = have
    return sections


TP_KEYWORDS = {
    "ceo": [
        "金管局", "證監", "hkma", "sfc", "stablecoin", "穩定幣", "虛擬銀行",
        "virtual bank", "digital bank", "牌照", "licence", "license", "監管",
        "regulati", "競爭", "competition", "代幣", "token", "crypto",
        "數碼資產", "digital asset",
    ],
    "business": [
        "推出", "launch", "客戶", "customer", "產品", "product", "優惠", "promo",
        "mox", "za bank", "livi", "welab", "airstar", "fusion", "paobank",
        "ant bank", "hsbc", "hang seng", "恒生", "匯豐", "中銀", "渣打", "citi",
        "standard chartered", "市佔", "market share",
    ],
    "treasury": [
        "hibor", "拆息", "存款", "deposit", "利率", "息率", "流動", "liquidity",
        "總結餘", "aggregate balance", "基本利率", "base rate", "定期",
        "time deposit", "同業", "interbank",
    ],
}
TP_LABELS = (
    ("ceo", "CEO",
     "Strategy, regulation, competition, virtual banks, HKMA and SFC, stablecoins and digital assets."),
    ("business", "Business heads",
     "Product, customer and market moves by competitors."),
    ("treasury", "Treasury and deposits",
     "Rate moves, liquidity, deposit competition and promo trends."),
)


def urls_in_payload(payload):
    found = set()
    for groups in (payload or {}).values():
        if not isinstance(groups, list):
            continue
        for group in groups:
            if not isinstance(group, list):
                continue
            for item in group:
                if isinstance(item, dict) and item.get("url"):
                    found.add(item["url"])
    return found


def url_allowed(url, allowed):
    if not url or not allowed:
        return False
    if url in allowed:
        return True
    base = url.split("#", 1)[0].split("?", 1)[0].rstrip("/")
    if len(base) < 24:
        return False
    return any(a.split("#", 1)[0].split("?", 1)[0].rstrip("/") == base for a in allowed)


def package_talking(buckets, mode):
    audiences = []
    for key, label, blurb in TP_LABELS:
        rows = (buckets or {}).get(key) or []
        if not rows:
            continue
        audiences.append({
            "id": key, "label": label, "blurb": blurb, "items": rows[:3],
        })
    return {"mode": mode, "audiences": audiences}


def clean_talking(raw, allowed):
    """Drop any bullet that does not cite a url from the articles we sent."""
    if not isinstance(raw, dict):
        return None
    alias = {
        "ceo": "ceo", "business": "business", "business_heads": "business",
        "treasury": "treasury", "treasury_and_deposits": "treasury",
    }
    found = {key: [] for key, _, _ in TP_LABELS}
    kept = 0
    for key, rows in raw.items():
        norm = str(key).strip().lower().replace("&", "and").replace(" ", "_")
        aud = alias.get(norm)
        if not aud or not isinstance(rows, list):
            continue
        for row in rows:
            if len(found[aud]) >= 3 or not isinstance(row, dict):
                continue
            point = clean(row.get("point") or row.get("headline") or "")
            if not point:
                continue
            so_what = clean(row.get("so_what") or row.get("sowhat") or "")
            so_what = re.sub(r"\s+", " ", so_what).strip()
            if len(so_what) > 280:
                so_what = so_what[:277].rstrip() + "..."
            sources = []
            seen = set()
            for src in row.get("sources") or []:
                if not isinstance(src, dict):
                    continue
                url = (src.get("url") or "").strip()
                if not url_allowed(url, allowed) or url in seen:
                    continue
                seen.add(url)
                sources.append({"name": clean(src.get("name") or "source")[:80], "url": url})
            if not sources:
                continue
            found[aud].append({"point": point[:400], "so_what": so_what, "sources": sources[:3]})
            kept += 1
    return found if kept else None


def rss_talking(collected):
    """Headline-only bullets. No angle, because there is no model to write one."""
    pools = []
    for key in ("work", "smalltalk_hk"):
        for group in collected.get(key) or []:
            if group:
                pools.append(group[0])
    buckets = {key: [] for key, _, _ in TP_LABELS}
    used = []
    for item in pools:
        if not item.get("url") or not item.get("title"):
            continue
        blob = (item.get("title", "") + " " + item.get("snippet", "")).lower()
        scores = {aud: sum(word in blob for word in words)
                  for aud, words in TP_KEYWORDS.items()}
        if not any(scores.values()):
            continue
        if any(similar(item["title"], title) > 0.82 for title in used):
            continue
        for aud in sorted(scores, key=lambda k: scores[k], reverse=True):
            if scores[aud] <= 0 or len(buckets[aud]) >= 3:
                continue
            buckets[aud].append({
                "point": item["title"],
                "title": item["title"],
                "so_what": "",
                "headline_only": True,
                "sources": [{"name": item.get("source") or "source", "url": item["url"]}],
            })
            used.append(item["title"])
            break
    return buckets


# ---------------------------------------------------------------- mute rules
#
# The page is public and never calls the GitHub API. "✕ Not for me" is only a
# prefilled new-issue link. This build reads those issues with the Action's
# GITHUB_TOKEN, turns them into filters, and drops matching stories before
# they are sent to the model. The merged rules are written to
# data/mute_rules.json so they remain after an issue is deleted.

REPO_SLUG = "poohpoohsy/morning-brief"
MUTE_PATH = ROOT / "data" / "mute_rules.json"
_DISPLAY = {
    "work": "Work",
    "talking_points": "Talking points",
    "smalltalk_hk": "Small Talk",
    "smalltalk_sg": "Small Talk",
    "personal_hk": "Personal",
    "personal_sg": "Personal",
    "juicy_hk": "Juicy",
    "juicy_sg": "Juicy",
}
_SECTION_GROUPS = (
    ("Work", ["work"]),
    ("Talking points", ["talking_points"]),
    ("Small Talk", ["smalltalk_hk", "smalltalk_sg"]),
    ("Personal", ["personal_hk", "personal_sg"]),
    ("Juicy", ["juicy_hk", "juicy_sg"]),
)


def section_keys(name):
    """Map a section label from a mute issue onto feed keys."""
    raw = (name or "").strip().casefold().replace("·", " ").replace("|", " ").replace("•", " ")
    raw = re.sub(r"\s+", " ", raw).strip()
    table = {
        "work": ["work"],
        "talking points": ["talking_points"],
        "talking_points": ["talking_points"],
        "small talk": ["smalltalk_hk", "smalltalk_sg"],
        "smalltalk": ["smalltalk_hk", "smalltalk_sg"],
        "small talk hong kong": ["smalltalk_hk"],
        "small talk singapore": ["smalltalk_sg"],
        "smalltalk_hk": ["smalltalk_hk"],
        "smalltalk_sg": ["smalltalk_sg"],
        "personal": ["personal_hk", "personal_sg"],
        "personal 香港民生": ["personal_hk"],
        "personal singapore government": ["personal_sg"],
        "personal_hk": ["personal_hk"],
        "personal_sg": ["personal_sg"],
        "juicy": ["juicy_hk", "juicy_sg"],
        "juicy 香港": ["juicy_hk"],
        "juicy singapore": ["juicy_sg"],
        "juicy_hk": ["juicy_hk"],
        "juicy_sg": ["juicy_sg"],
    }
    if raw in table:
        return list(table[raw])
    for key, sec in CFG["sections"].items():
        label = re.sub(r"\s+", " ", sec.get("label", "").casefold().replace("·", " ")).strip()
        if raw == label:
            return [key]
    return []


def _display_name(keys):
    names = []
    for key in keys:
        name = _DISPLAY.get(key, key)
        if name not in names:
            names.append(name)
    return names[0] if len(names) == 1 else ", ".join(names)


def _field(body, name):
    match = re.search(rf"(?mi)^{re.escape(name)}\s*[:：]\s*(.*)$", body or "")
    return match.group(1).strip() if match else ""


def _form_field(body, label):
    match = re.search(
        rf"(?ims)^###\s*{re.escape(label)}\s*\n+(.*?)(?=^###\s|\Z)", body or "")
    return match.group(1).strip() if match else ""


def _split_terms(text):
    out = []
    for part in re.split(r"[,，、;；|]+", text or ""):
        term = part.strip().strip("\"'“”‘’").strip()
        if len(term) < 2 or term in out:
            continue
        out.append(term)
        if len(out) >= 8:
            break
    return out


def _checked_boxes(body):
    """Which of the three mute boxes were ticked. Unticked boxes are ignored."""
    found = {"source": False, "terms": False, "section": False}
    phrases = (
        ("source", "mute this source"),
        ("terms", "mute these words"),
        ("section", "mute the whole section"),
    )
    for line in (body or "").splitlines():
        match = re.search(r"\[([^\]]*)\]\s*(.+)", line)
        if not match:
            continue
        mark = match.group(1).strip().casefold()
        if mark not in {"x", "✓", "✔"}:
            continue
        label = match.group(2).strip().casefold()
        for key, phrase in phrases:
            if phrase in label:
                found[key] = True
    return found


def parse_mute_body(body):
    """Read one mute issue. None when it has no usable section or scope.

    Leaving every box unticked mutes the key terms, so submitting the prefilled
    issue is enough. Ticking a box limits the rule to what was ticked.
    """
    body = body or ""
    section = _field(body, "Section") or _form_field(body, "section")
    source = _field(body, "Source") or _form_field(body, "source")
    link = _field(body, "Link") or _form_field(body, "link")
    title = _field(body, "Title") or _form_field(body, "title")
    if _field(body, "Key terms") or re.search(r"(?mi)^Key terms\s*[:：]", body):
        terms_line = _field(body, "Key terms")
    else:
        terms_line = _form_field(body, "key terms")
    keys = section_keys(section)
    if not keys:
        return None
    boxes = _checked_boxes(body)
    any_checked = any(boxes.values())
    use_source = boxes["source"]
    use_terms = boxes["terms"] or not any_checked
    use_section = boxes["section"]
    sources = [source.strip()] if use_source and source.strip() else []
    terms = _split_terms(terms_line) if use_terms else []
    titles = []
    if use_terms and not terms and title.strip():
        titles.append(title.strip())
    if not (use_section or sources or terms or titles):
        return None
    return {
        "section": _display_name(keys),
        "keys": keys,
        "hide_section": bool(use_section),
        "sources": sources,
        "terms": terms,
        "titles": titles,
        "example_title": title.strip(),
        "example_url": link.strip(),
    }


def normalize_rule(rule):
    if not isinstance(rule, dict):
        return None
    keys = [k for k in (rule.get("keys") or []) if isinstance(k, str) and k]
    if not keys and rule.get("section"):
        keys = section_keys(rule.get("section"))
    if not keys:
        return None
    sources = []
    for src in rule.get("sources") or []:
        if isinstance(src, str) and src.strip() and src.strip() not in sources:
            sources.append(src.strip())
    terms = []
    for term in rule.get("terms") or []:
        if isinstance(term, str) and len(term.strip()) >= 2 and term.strip() not in terms:
            terms.append(term.strip())
    titles = []
    for title in rule.get("titles") or []:
        if isinstance(title, str) and title.strip() and title.strip() not in titles:
            titles.append(title.strip())
    issue = rule.get("issue")
    if not isinstance(issue, int):
        issue = None
    ident = rule.get("id")
    if not ident:
        ident = f"issue:{issue}" if issue else "manual:" + hashlib.sha1(
            json.dumps({
                "section": rule.get("section") or "",
                "keys": keys,
                "hide": bool(rule.get("hide_section")),
                "sources": sources,
                "terms": terms,
                "titles": titles,
            }, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
    return {
        "id": str(ident),
        "issue": issue,
        "section": rule.get("section") or _display_name(keys),
        "keys": keys,
        "hide_section": bool(rule.get("hide_section")),
        "sources": sources,
        "terms": terms,
        "titles": titles,
        "example_title": rule.get("example_title") or (titles[0] if titles else ""),
        "example_url": rule.get("example_url") or "",
    }


def load_saved_rules(path=None):
    data = load_json(Path(path) if path else MUTE_PATH, {"version": 1, "rules": []})
    raw = data if isinstance(data, list) else (data.get("rules") if isinstance(data, dict) else [])
    rules = []
    for rule in raw or []:
        cleaned = normalize_rule(rule)
        if cleaned:
            rules.append(cleaned)
    return rules


def merge_rules(saved, incoming):
    """Issues win when they still exist. A rule whose issue was deleted stays."""
    by_id = {}
    for rule in saved or []:
        cleaned = normalize_rule(rule)
        if cleaned:
            by_id[cleaned["id"]] = cleaned
    for rule in incoming or []:
        cleaned = normalize_rule(rule)
        if cleaned:
            by_id[cleaned["id"]] = cleaned
    return sorted(by_id.values(), key=lambda r: (r.get("issue") or 10**9, r.get("id") or ""))


def save_rules(rules, path=None):
    path = Path(path) if path else MUTE_PATH
    cleaned = []
    for rule in rules or []:
        item = normalize_rule(rule)
        if item:
            cleaned.append(item)
    cleaned = merge_rules([], cleaned)
    path.parent.mkdir(exist_ok=True)
    doc = {"version": 1, "rules": cleaned}
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return cleaned


def github_json(method, path, token, payload=None):
    """GitHub REST call. Returns (status, body). Body is None on a transport error."""
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com" + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "morning-brief",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:240]
        return e.code, detail
    except Exception as e:
        log(f"GitHub {method} {path} failed: {e}")
        return 0, None


def ensure_mute_label(repo, token):
    code, _ = github_json("POST", f"/repos/{repo}/labels", token, {
        "name": "mute",
        "color": "6e7781",
        "description": "Hide matching stories from future morning briefs",
    })
    if code in (201, 422):
        return
    log(f"Could not ensure the mute label (HTTP {code})")


def list_mute_issues(repo, token):
    """Open and closed issues labelled mute. None when the API cannot be read."""
    found = []
    for page in range(1, 11):
        code, data = github_json(
            "GET",
            f"/repos/{repo}/issues?state=all&labels=mute&per_page=100&page={page}",
            token,
        )
        if code != 200 or not isinstance(data, list):
            log(f"Could not list mute issues (HTTP {code})")
            return None
        found.extend(issue for issue in data if "pull_request" not in issue)
        if len(data) < 100:
            break
    return found


def rule_from_issue(issue):
    parsed = parse_mute_body(issue.get("body") or "")
    if not parsed:
        return None
    parsed["id"] = f"issue:{issue.get('number')}"
    parsed["issue"] = issue.get("number")
    return normalize_rule(parsed)


def close_applied_issue(repo, token, number):
    code, _ = github_json(
        "POST", f"/repos/{repo}/issues/{number}/comments", token, {"body": "Applied"})
    if code not in (200, 201):
        log(f"Mute issue #{number} parsed, but the Applied comment failed (HTTP {code})")
        return
    code, _ = github_json(
        "PATCH", f"/repos/{repo}/issues/{number}", token,
        {"state": "closed", "state_reason": "completed"})
    if code not in (200, 201):
        code, _ = github_json(
            "PATCH", f"/repos/{repo}/issues/{number}", token, {"state": "closed"})
    if code in (200, 201):
        log(f"Mute issue #{number} applied and closed")
    else:
        log(f"Mute issue #{number} commented, but it stayed open (HTTP {code})")


def sync_mute_rules():
    """Merge labelled issues into data/mute_rules.json. File-only when no token."""
    saved = load_saved_rules()
    token = (os.getenv("GITHUB_TOKEN") or "").strip()
    repo = (os.getenv("GITHUB_REPOSITORY") or REPO_SLUG).strip()
    if not token or token.lower() in {"none", "null"} or "/" not in repo:
        log(f"Mute rules: {len(saved)} from data/mute_rules.json (no GitHub token)")
        return save_rules(saved)
    ensure_mute_label(repo, token)
    issues = list_mute_issues(repo, token)
    if issues is None:
        log("Mute rules: GitHub issues unavailable, keeping the saved file")
        return save_rules(saved)
    parsed = []
    close = []
    for issue in issues:
        rule = rule_from_issue(issue)
        if not rule:
            log(f"Mute issue #{issue.get('number')} left open — no section to apply")
            continue
        parsed.append(rule)
        if issue.get("state") == "open":
            close.append(issue.get("number"))
    merged = merge_rules(saved, parsed)
    save_rules(merged)
    log(f"Mute rules: {len(merged)} active ({len(parsed)} from issues)")
    for number in close:
        if number:
            close_applied_issue(repo, token, number)
    return merged


def section_hidden(rules, key):
    return any(r.get("hide_section") and key in (r.get("keys") or []) for r in rules)


def hidden_section_labels(rules):
    labels = []
    for label, keys in _SECTION_GROUPS:
        if all(section_hidden(rules, key) for key in keys):
            labels.append(label)
    return labels


def _card_bits(item):
    parts = []
    sources = []
    if not isinstance(item, dict):
        return "", []
    for key in ("title", "headline", "point", "body", "en", "snippet", "so_what", "tag", "source"):
        value = item.get(key)
        if isinstance(value, str):
            parts.append(value)
    for line in item.get("zh") or []:
        if isinstance(line, str):
            parts.append(line)
    if isinstance(item.get("source"), str):
        sources.append(item["source"])
    for src in item.get("sources") or []:
        if isinstance(src, dict):
            if isinstance(src.get("name"), str):
                sources.append(src["name"])
                parts.append(src["name"])
    return " ".join(parts), sources


def _source_hit(item_sources, rule_sources):
    names = [re.sub(r"\s+", " ", s).strip().casefold()
             for s in item_sources if isinstance(s, str)]
    names = [n for n in names if n]
    for rule in rule_sources or []:
        needle = re.sub(r"\s+", " ", rule or "").strip().casefold()
        if len(needle) < 2:
            continue
        if any(name == needle or needle in name for name in names):
            return True
    return False


def _terms_hit(blob, terms):
    needles = [t.casefold().strip() for t in (terms or [])
               if isinstance(t, str) and len(t.strip()) >= 2]
    if not needles:
        return False
    hay = (blob or "").casefold()
    return all(n in hay for n in needles)


def _title_hit(title, titles):
    if not title:
        return False
    for other in titles or []:
        if other and similar(title, other) >= 0.92:
            return True
    return False


def _item_title(item):
    for key in ("title", "headline", "point"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for line in item.get("zh") or []:
        if isinstance(line, str) and line.strip() and not line.strip().startswith("（只有標題"):
            return line.strip()
    return ""


def item_is_muted(item, rules, key):
    blob, sources = _card_bits(item)
    title = _item_title(item)
    for rule in rules or []:
        if key not in (rule.get("keys") or []):
            continue
        if rule.get("hide_section"):
            return True
        if _source_hit(sources, rule.get("sources")):
            return True
        if _terms_hit(blob, rule.get("terms")):
            return True
        if _title_hit(title, rule.get("titles")):
            return True
    return False


def candidates_for_model(items_by_key, rules):
    """Drop muted stories before clustering, so they never reach the model."""
    collected = {}
    payload = {}
    stats = {"dropped": 0, "hidden": []}
    for key, items in items_by_key.items():
        if section_hidden(rules, key):
            collected[key] = []
            stats["hidden"].append(key)
            log(f"[{key}] whole section muted — not sent to the model")
            continue
        kept = []
        dropped = 0
        for item in items or []:
            if item_is_muted(item, rules, key):
                dropped += 1
            else:
                kept.append(item)
        if dropped:
            stats["dropped"] += dropped
            log(f"[{key}] muted {dropped} item{'s' if dropped != 1 else ''} before the model")
        groups = cluster(kept)
        collected[key] = groups
        # Same shape as before: every remaining cluster, three members, short snippet.
        payload[key] = [
            [{"title": m["title"], "source": m["source"], "url": m["url"],
              "published": m.get("published", ""), "snippet": (m.get("snippet") or "")[:280]}
             for m in g[:3]]
            for g in groups
        ]
    return collected, payload, stats


def filter_output(sections, rules):
    out = {}
    for key, items in (sections or {}).items():
        if not isinstance(items, list):
            continue
        if section_hidden(rules, key):
            out[key] = []
            continue
        out[key] = [it for it in items
                    if isinstance(it, dict) and not item_is_muted(it, rules, key)]
    for key in CFG["sections"]:
        out.setdefault(key, [])
        if section_hidden(rules, key):
            out[key] = []
    return out


def filter_talking(talking, rules):
    if not isinstance(talking, dict):
        talking = {"mode": "rss", "audiences": []}
    if section_hidden(rules, "talking_points"):
        return {"mode": "muted", "audiences": []}
    audiences = []
    for aud in talking.get("audiences") or []:
        if not isinstance(aud, dict):
            continue
        items = [it for it in (aud.get("items") or [])
                 if isinstance(it, dict) and not item_is_muted(it, rules, "talking_points")]
        if not items:
            continue
        kept = dict(aud)
        kept["items"] = items
        audiences.append(kept)
    return {"mode": talking.get("mode") or "rss", "audiences": audiences}


def remember_titles(sections, talking, collected):
    """Keep the feed headline on each card so the mute link names the story."""
    by_url = {}
    for groups in (collected or {}).values():
        for group in groups or []:
            for item in group or []:
                if isinstance(item, dict) and item.get("url") and item.get("title"):
                    by_url.setdefault(item["url"], item["title"])

    def stamp(item):
        if not isinstance(item, dict) or item.get("title"):
            return
        for src in item.get("sources") or []:
            url = src.get("url") if isinstance(src, dict) else ""
            if url and url in by_url:
                item["title"] = by_url[url]
                return

    for items in (sections or {}).values():
        for item in items or []:
            stamp(item)
    for aud in (talking or {}).get("audiences") or []:
        for item in aud.get("items") or []:
            stamp(item)


def mute_summaries(rules):
    rows = []
    for rule in rules or []:
        bits = []
        if rule.get("hide_section"):
            bits.append("whole section")
        for src in rule.get("sources") or []:
            bits.append("source: " + src)
        if rule.get("terms"):
            bits.append("words: " + ", ".join(rule["terms"]))
        if rule.get("titles") and not rule.get("terms"):
            bits.append("title: " + rule["titles"][0][:80])
        text = rule.get("section") or "Section"
        if bits:
            text += " — " + "; ".join(bits)
        rows.append({"section": rule.get("section") or "", "summary": text})
    return rows


def main():
    rules = sync_mute_rules()
    fetched = {}
    for key, sec in CFG["sections"].items():
        # A muted section is not fetched and not sent to the model.
        if section_hidden(rules, key):
            fetched[key] = []
        else:
            fetched[key] = fetch_section(key, sec)
    collected, payload, mute_stats = candidates_for_model(fetched, rules)
    # No fixed per-section cap. The shared character budget trims a busy day
    # without cutting a quiet one. Muted stories are already gone.
    payload = fit_budget(payload)
    # Market data first, so a slow model call cannot skip the history update.
    market = build_market()

    skip_talking = section_hidden(rules, "talking_points")
    muted_keys = list(mute_stats["hidden"])
    nothing_left = not any(payload.values())
    muted_all = nothing_left and (mute_stats["dropped"] or mute_stats["hidden"] or skip_talking)

    if muted_all:
        log("Mute rules left nothing to summarise — model not called")
        sections, method = rss_digest(collected), "muted"
        talking = {"mode": "muted", "audiences": []}
    else:
        try:
            sections, method = call_model(
                payload, skip_talking=skip_talking, muted_keys=muted_keys)
            if not isinstance(sections, dict):
                raise ValueError("model reply was not a JSON object")
            raw_points = sections.pop("talking_points", None)
            sections = top_up(sections, collected)
            if skip_talking:
                talking = {"mode": "muted", "audiences": []}
                log("Talking points: section muted")
            else:
                cleaned = clean_talking(raw_points, urls_in_payload(payload))
                if cleaned:
                    talking = package_talking(cleaned, "model")
                    log("Talking points: from the model")
                else:
                    talking = package_talking(rss_talking(collected), "rss")
                    log("Talking points: no sourced model bullets — headline-only fallback")
        except Exception as e:
            log(f"Model step skipped or failed ({e}) — using RSS summaries")
            sections, method = rss_digest(collected), "rss-only"
            if skip_talking:
                talking = {"mode": "muted", "audiences": []}
                log("Talking points: section muted")
            else:
                talking = package_talking(rss_talking(collected), "rss")
                log("Talking points: headline-only (no model)")

    remember_titles(sections, talking, collected)
    sections = filter_output(sections, rules)
    talking = filter_talking(talking, rules)

    now = datetime.now(HK)
    out = {
        "report_date": now.strftime("%A, %-d %B %Y") if os.name != "nt" else now.strftime("%A, %d %B %Y"),
        "generated_at": now.strftime("%d %b %Y %H:%M HKT"),
        "generated_iso": now.isoformat(),
        "build": {"method": method, "log": LOG},
        "repo": os.getenv("GITHUB_REPOSITORY") or REPO_SLUG,
        "weather": weather(),
        "hkma": market["hkma"],
        "hkma_bars": market["bars"],
        "treasury": market["treasury"],
        "talking_points": talking,
        "rates": rate_table(),
        "labels": {k: v["label"] for k, v in CFG["sections"].items()},
        "sections": sections,
        "hidden_sections": hidden_section_labels(rules),
        "mutes": mute_summaries(rules),
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
  .staletag{display:inline-block;margin-left:8px;padding:1px 6px;border-radius:5px;
    background:var(--warn-bg);color:var(--warn-ink);font-size:10.5px;font-weight:700;
    letter-spacing:.04em;text-transform:uppercase;vertical-align:1px}
  .stats{display:grid;grid-template-columns:1fr 1fr;gap:12px 16px;margin-top:14px}
  .stat .k{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);font-weight:700}
  .stat .v{font-size:22px;font-weight:720;letter-spacing:-.02em;margin-top:2px}
  .stat .s{font-size:12.5px;color:var(--ink2);margin-top:3px;line-height:1.45}
  .band{margin-top:8px}
  .bandtrack{position:relative;height:8px;border-radius:99px;
    background:linear-gradient(90deg,var(--up),var(--bar) 55%,var(--down))}
  .bandmark{position:absolute;top:-4px;width:3px;height:16px;border-radius:2px;
    background:var(--ink);transform:translateX(-50%)}
  .bandlabs{display:flex;justify-content:space-between;font-size:10.5px;color:var(--muted);margin-top:5px}
  .sowhat{margin:6px 0 0;font-size:13.5px;line-height:1.45;color:var(--ink2);
    border-left:2px solid var(--talk);padding-left:9px}
  .unavail{color:var(--muted);font-size:13px}
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
  .tag{font-size:10.5px;font-weight:700;padding:2px 7px;border-radius:5px;
    background:var(--juicy-bg);color:var(--juicy-ink);letter-spacing:.02em}
  .quiet{margin-top:8px;font-size:12px;line-height:1.45;color:var(--muted);
    border-left:2px solid var(--muted);padding-left:9px}
  .jhead{display:flex;align-items:center;gap:7px;margin-bottom:6px}
  .mute-row{display:flex;justify-content:flex-end}
  .mute{display:inline-flex;align-items:center;min-height:32px;margin-top:4px;
    padding:4px 8px;border-radius:8px;border:1px solid transparent;
    font-size:11.5px;font-weight:650;color:var(--muted);text-decoration:none}
  .mute:hover,.mute:active,.mute:focus-visible{
    color:var(--ink2);border-color:var(--line);background:var(--hair)}
  footer{margin-top:26px;color:var(--muted);font-size:11.5px;line-height:1.6}
  .mutes{margin-top:4px}
  .mutes summary{color:var(--muted);font-size:12px;font-weight:650}
  .mutes ul{margin:8px 0 0;padding-left:18px}
  .mutes li{margin:3px 0}
  .mutes-empty,.mutes-hint{margin:6px 0 0}
  .foot-note{margin-top:12px}
  @media(max-width:560px){h1{font-size:25px}.bars{height:58px}.stats{grid-template-columns:1fr}}
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
    <div class="asof">HKMA daily figures, ${esc(h.as_of)}. Each bar is a closing aggregate balance.</div>
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
  const virtuals = r.rows.filter(x => x.kind === "virtual").length;
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
    <div class="asof">${r.rows.length} banks tracked${virtuals ? `, ${virtuals} virtual` : ""}${r.placeholders ? ` &middot; <span style="color:var(--down)">${r.placeholders} placeholder value${r.placeholders===1?"":"s"} — edit data/rates_manual.json</span>` : ""}. Virtual-bank rows are typed in by hand.</div>
    <table class="mono"><thead><tr><th></th><th>Bank</th><th class="r">Rate</th><th class="r">1d</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <div class="cutlab">Dashed line = top 10 cut-off.</div>
    ${movers ? `<div class="newpromo"><div class="h">Moved today · 3 max</div>${movers}</div>` : ""}
  </section>`;
}

function moneyBn(v, signed){
  if(v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
  const bn = Number(v) / 1000;
  const body = "$" + Math.abs(bn).toFixed(1) + "bn";
  if(!signed) return (bn < 0 ? "-" : "") + body;
  if(Math.abs(bn) < 0.05) return "unchanged";
  return (bn > 0 ? "+" : "−") + body;
}
function bpText(bp){
  if(bp === null || bp === undefined || Number.isNaN(Number(bp))) return "—";
  const n = Number(bp);
  if(Math.abs(n) < 0.05) return "—";
  const shown = Math.abs(n) >= 10 ? n.toFixed(0) : n.toFixed(1);
  return `<span class="${n>0?'up':'down'}">${n>0?'+':''}${shown}bp</span>`;
}
function rateText(v){
  if(v === null || v === undefined || Number.isNaN(Number(v))) return "n/a";
  const n = Number(v);
  let s = n.toFixed(5).replace(/0+$/,"").replace(/\.$/,"");
  const dec = (s.split(".")[1] || "");
  if(dec.length < 2) s = n.toFixed(2);
  return s;
}
function staleTag(on){ return on ? `<span class="staletag">stale</span>` : ""; }

function treasuryPanel(t, bars){
  if(!t) return "";
  const bal = t.balance || {};
  const hibor = t.hibor || {};
  const fx = t.fx || {};
  const spread = t.spread || {};
  let head = `<div class="unavail">Aggregate balance unavailable.</div>`;
  if(bal.available && bal.value_hkdm != null){
    const move = (bal.change_hkdm === null || bal.change_hkdm === undefined) ? ""
      : (Math.abs(bal.change_hkdm) < 1
          ? `<span class="bigmeta">vs previous session <b>unchanged</b></span>`
          : `<span class="bigmeta">vs previous session <b class="${bal.change_hkdm>0?'up':'down'}">${moneyBn(bal.change_hkdm, true)}</b>${bal.flat_sessions>1?` · ${bal.flat_sessions} sessions flat`:""}</span>`);
    const base = bal.base_rate == null ? "n/a" : rateText(bal.base_rate) + "%";
    const baseChg = bal.base_rate_change_bp == null ? "" : " " + bpText(bal.base_rate_change_bp);
    head = `<div class="big"><span class="bigval mono">${moneyBn(bal.value_hkdm, false)}</span>${move}</div>
      <div class="bigmeta">Base rate <b>${base}</b>${baseChg}</div>`;
  }
  const parts = (bal.components || []).map(c =>
    `<b>${esc(c.label)}</b> ${moneyBn(c.hkdm, true)}`).join(" · ");
  const partNote = parts ? `<div class="notes">Day's published drivers: ${parts}.</div>` : "";

  let chart = "";
  const series = (bars || []).filter(b => b && b.value != null);
  if(series.length >= 2){
    const min = Math.min(...series.map(b => b.value));
    const max = Math.max(...series.map(b => b.value));
    const pad = Math.max((max - min) * 0.18, 1);
    const lo = min - pad, hi = max + pad;
    const peak = series.reduce((a,b) => b.value > a.value ? b : a, series[0]);
    const low = series.reduce((a,b) => b.value < a.value ? b : a, series[0]);
    const cols = bars.map((b,i) => {
      const v = b.value == null ? min : b.value;
      const h = Math.max(2, Math.min(100, (v - lo) / (hi - lo) * 100));
      const last = i === bars.length - 1;
      const cls = last ? "now" : (b.date === peak.date ? "hi" : (b.date === low.date ? "lo" : ""));
      return `<div class="bcol"><div class="b ${cls}" style="height:${h.toFixed(1)}%"></div></div>`;
    }).join("");
    const labs = bars.map((b,i) => {
      const show = i === bars.length - 1 || i % 6 === 0;
      const text = i === bars.length - 1 ? "now" : String(b.year || "");
      return `<span>${show ? esc(text) : ""}</span>`;
    }).join("");
    const win = bal.window_change_hkdm;
    const winTxt = (win === null || win === undefined) ? ""
      : ` Over these ${series.length} sessions it ${win > 0 ? "rose" : win < 0 ? "fell" : "was unchanged"}${win ? " by " + moneyBn(Math.abs(win), false) : ""}.`;
    const behind = bal.history_behind
      ? ` Chart ends ${esc(bal.history_through)}; the headline is a later print that is not in the saved series.`
      : "";
    chart = `<div class="bars">${cols}</div><div class="blab">${labs}</div>
      <div class="notes">Each bar is a business day's closing aggregate balance, scaled to this window so the move is visible.
        <b>High</b> ${moneyBn(peak.value, false)} on ${esc(peak.date || "")} · <b>Low</b> ${moneyBn(low.value, false)} on ${esc(low.date || "")}.${winTxt}${behind}</div>`;
  } else if(bal.available){
    chart = `<div class="notes">History is still building — the chart appears once a few sessions have accumulated.</div>`;
  }

  let hiborHtml = `<div class="unavail">HIBOR unavailable.</div>`;
  if(hibor.available && (hibor.tenors || []).length){
    const rows = hibor.tenors.map(x => `<tr>
      <td>${esc(x.label)}${hibor.mixed_dates && x.as_of ? `<span class="kind">${esc(String(x.as_of).slice(5))}</span>` : ""}</td>
      <td class="r rate">${x.rate == null ? "unavailable" : rateText(x.rate) + "%"}</td>
      <td class="r chg">${x.rate == null ? "" : bpText(x.change_bp)}</td></tr>`).join("");
    const hiborWhen = hibor.mixed_dates ? "" : (hibor.as_of ? ", " + esc(hibor.as_of) : "");
    const hiborChg = hibor.mixed_dates || !hibor.prev_date ? "" : " · change vs " + esc(hibor.prev_date);
    hiborHtml = `<div class="ptitle" style="margin-top:16px">HIBOR${staleTag(hibor.stale)}</div>
      <div class="asof">${esc(hibor.source || "HKMA")}${hiborWhen}${hiborChg}</div>
      <table class="mono"><thead><tr><th>Tenor</th><th class="r">Rate</th><th class="r">1d</th></tr></thead>
      <tbody>${rows}</tbody></table>
      ${hibor.partial ? `<div class="notes">1-week, 3-month, 6-month and 12-month did not load. Overnight and 1-month are the figures carried on the daily liquidity release.</div>` : ""}
      ${hibor.mixed_dates ? `<div class="notes">Overnight and 1-month are the daily liquidity release of ${esc(hibor.daily_as_of)}. 1-week and longer are the HKAB fixing of ${esc(hibor.curve_as_of)}, the latest date that series has published. Each 1d change is versus the previous session of the same series.</div>` : ""}`;
  }

  let fxHtml = `<div class="stat"><div class="k">USD/HKD</div><div class="v unavail">unavailable</div></div>`;
  if(fx.available && fx.spot != null){
    const pct = Math.max(0, Math.min(100, Number(fx.pct_through_band) || 0));
    let where;
    if(Number(fx.pips_to_weak) < 0) where = `${Math.abs(fx.pips_to_weak)} pips through the weak-side convertibility undertaking`;
    else if(Number(fx.pips_to_strong) < 0) where = `${Math.abs(fx.pips_to_strong)} pips through the strong-side convertibility undertaking`;
    else where = `${fx.pips_to_weak} pips from the weak-side convertibility undertaking`;
    fxHtml = `<div class="stat"><div class="k">USD/HKD${staleTag(fx.stale)}</div>
      <div class="v mono">${Number(fx.spot).toFixed(4)}</div>
      <div class="band" aria-hidden="true"><div class="bandtrack"><div class="bandmark" style="left:${pct.toFixed(1)}%"></div></div>
        <div class="bandlabs"><span>${Number(fx.strong).toFixed(2)} strong</span><span>${Number(fx.weak).toFixed(2)} weak</span></div></div>
      <div class="s">${where}${fx.change_pips == null ? "" : ` · ${fx.change_pips > 0 ? "+" : ""}${fx.change_pips} pips vs ${esc(fx.prev_date || "previous")}`}. ${esc(fx.source || "")}${fx.as_of ? ", " + esc(fx.as_of) : ""}.</div></div>`;
  }
  const checked = fx.sessions_checked || 0;
  const hits = fx.market_activities || [];
  const hitTxt = hits.length
    ? hits.map(h => `${esc(h.date)} ${moneyBn(h.hkdm, true)}`).join("; ")
    : (checked ? `flat over the last ${checked} sessions` : "not loaded");
  const casts = fx.fx_forecast || [];
  const castTxt = casts.length
    ? casts.map(c => `${esc(c.when)} ${moneyBn(c.hkdm, true)}`).join(", ")
    : "none in the latest figures";
  const flowHtml = `<div class="notes"><b>Weak-side liquidity.</b> HKMA market activities (spot FX and other money-market operations — a weak-side convertibility-undertaking hit shows up here as a drain): ${hitTxt}. Forecast FX flow into the aggregate balance: ${castTxt}.</div>`;

  let spreadHtml = `<div class="stat"><div class="k">HKD vs USD</div><div class="v unavail">unavailable</div>
    <div class="s">${esc((spread && spread.note) || "No public 1-month spread today.")}</div></div>`;
  if(spread && spread.available && spread.spread_bp != null){
    spreadHtml = `<div class="stat"><div class="k">${esc(spread.label)}${staleTag(spread.stale)}</div>
      <div class="v">${bpText(spread.spread_bp)}</div>
      <div class="s">1M HIBOR ${rateText(spread.hibor_1m)}% (${esc(spread.hibor_as_of || "")}) minus ${esc(spread.usd_label)} ${rateText(spread.usd_rate)}% (${esc(spread.usd_as_of || "")}). ${esc(spread.note || "")}</div></div>`;
  }

  const staleNote = bal.stale
    ? `<div class="notes">Stale: this run could not refresh HKMA, so these are the last good figures${bal.as_of ? " (" + esc(bal.as_of) + ")" : ""}. Not a new print.</div>`
    : "";
  return `<section class="panel">
    <div class="ptitle">Treasury${staleTag(bal.stale)}</div>
    <div class="asof">Aggregate balance${bal.as_of ? ", HKMA daily figures " + esc(bal.as_of) : ""}. HIBOR fixings, the base rate, and USD/HKD in the convertibility band.</div>
    ${staleNote}${head}${partNote}${chart}${hiborHtml}
    <div class="stats">${fxHtml}${spreadHtml}</div>
    ${flowHtml}
  </section>`;
}

function talkingCard(it){
  const sowhat = it.so_what
    ? `<p class="sowhat"><b>So what.</b> ${esc(it.so_what)}</p>` : "";
  return `<article class="card">
    <h3 class="headline">${esc(it.point || it.headline || "")}</h3>
    ${sowhat}
    ${srcLine(it.sources)}
    ${muteBtn(it, "Talking points")}</article>`;
}
function talkingSection(tp){
  const audiences = ((tp && tp.audiences) || []).filter(a => (a.items || []).length);
  if(!audiences.length) return "";
  const intro = tp.mode === "rss"
    ? `<p class="notes">Headline only. The summary model did not run, so there is no "so what" line and nothing here was inferred.</p>`
    : "";
  const body = audiences.map(a => `<div class="sub2">${esc(a.label)}</div>
    ${a.blurb ? `<div class="asof">${esc(a.blurb)}</div>` : ""}
    ${a.items.slice(0,3).map(talkingCard).join("")}`).join("");
  const total = audiences.reduce((n,a) => n + Math.min(3, a.items.length), 0);
  return `<section class="section">
    <div class="shead"><span class="dot" style="background:var(--talk)"></span>
      <h2>Talking points</h2><span class="scount">${total} item${total===1?"":"s"}</span></div>
    ${intro}${body}</section>`;
}

const TERM_STOP = new Set(("a an the and or of to in on for with from by at as is are was were be been " +
  "it its this that these those after over into about says said new more will has have had not but their " +
  "his her who what when where how why amid via per than then also just may can could would should " +
  "reportedly report reports news says say before under out update updates latest breaking " +
  "hong kong singapore today yesterday year week month " +
  "的 了 在 是 與 及 和 為 將 被 對 從 也 或 並 而 但 就 都 很 到 以 等 其 這 那 有 不 未 已 " +
  "香港 港元 今日 昨日 今年 表示 指出").split(/\s+/));

function repoSlug(v){
  const s = String(v || "poohpoohsy/morning-brief");
  return /^[\w.-]+\/[\w.-]+$/.test(s) ? s : "poohpoohsy/morning-brief";
}

function itemTitle(it){
  if(it.title && String(it.title).trim()) return String(it.title).trim();
  if(it.headline && String(it.headline).trim()) return String(it.headline).trim();
  if(it.point && String(it.point).trim()) return String(it.point).trim();
  const post = String(it.en || "").match(/The post (.+?) appeared first on /);
  if(post && post[1].trim()) return post[1].trim();
  for(const line of (it.zh || [])){
    const s = String(line || "").trim();
    if(s && !s.startsWith("（只有標題")) return s;
  }
  return "item";
}

function keyTerms(title){
  const text = String(title || "");
  const latin = [];
  const re = /[A-Za-z][A-Za-z0-9'+-]{2,}/g;
  let m;
  while((m = re.exec(text))){
    const low = m[0].replace(/^'+|'+$/g, "").toLowerCase();
    if(low.length < 4 || TERM_STOP.has(low) || latin.includes(low)) continue;
    latin.push(low);
  }
  const ranked = latin.slice().sort((a, b) => b.length - a.length).slice(0, 4);
  const picked = latin.filter(w => ranked.includes(w)).slice(0, 4);
  const cjk = [];
  for(const run of (text.match(/[\u4e00-\u9fff]{2,}/g) || [])){
    if(TERM_STOP.has(run)) continue;
    const chunks = run.length <= 6 ? [run] : [run.slice(0, 4), run.slice(4, 8)].filter(Boolean);
    for(const chunk of chunks){
      if(chunk.length >= 2 && !TERM_STOP.has(chunk) && !cjk.includes(chunk)) cjk.push(chunk);
      if(cjk.length >= 4) break;
    }
    if(cjk.length >= 4) break;
  }
  const terms = picked.length >= 2 ? picked : cjk.concat(picked);
  const out = [];
  for(const t of terms){
    if(!out.includes(t)) out.push(t);
    if(out.length >= 4) break;
  }
  return out;
}

function muteLink(repo, section, it){
  const title = itemTitle(it);
  const src = (it.sources && it.sources[0]) || {};
  const source = it.source || src.name || "";
  const link = it.url || src.url || "";
  const terms = keyTerms(title);
  const body = [
    "Mute this from future briefs. Edit the key terms if they are off, then submit.",
    "If you leave the boxes unticked, those key terms are muted in this section.",
    "",
    "Section: " + section,
    "Source: " + source,
    "Link: " + link,
    "Title: " + title,
    "",
    "Key terms: " + terms.join(", "),
    "",
    "- [ ] Mute this source in this section",
    "- [ ] Mute these words",
    "- [ ] Mute the whole section",
  ].join("\n");
  const params = new URLSearchParams();
  params.set("labels", "mute");
  const heading = "Mute: " + title;
  params.set("title", heading.length > 240 ? heading.slice(0, 237) + "..." : heading);
  params.set("body", body);
  return "https://github.com/" + repo + "/issues/new?" + params.toString();
}

let REPO = "poohpoohsy/morning-brief";
function muteBtn(it, section){
  const href = muteLink(REPO, section, it);
  return `<div class="mute-row"><a class="mute" href="${esc(href)}" target="_blank" rel="noopener">✕ Not for me</a></div>`;
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
    ${muteBtn(it, "Work")}
  </article>`;
}

function juicyCard(it){
  return `<article class="card">
    <div class="jhead">${it.tag ? `<span class="tag">${esc(it.tag)}</span>` : ""}</div>
    <h3 class="headline">${esc(it.headline)}</h3>
    ${it.body ? `<p class="two">${esc(it.body)}</p>` : ""}
    ${it.raise === false
      ? `<div class="quiet">知道就得 &middot; 唔使主動提 — the other person's answer would expose a political position.</div>`
      : ""}
    ${srcLine(it.sources)}
    ${muteBtn(it, "Juicy")}</article>`;
}
function plainCard(it, section){
  return `<article class="card">
    <h3 class="headline">${esc(it.headline)}</h3>
    ${it.body ? `<p class="two">${esc(it.body)}</p>`
              : `<p class="two" style="opacity:.6">Headline only - open the source.</p>`}
    ${srcLine(it.sources)}
    ${muteBtn(it, section)}</article>`;
}

function render(D){
  REPO = repoSlug(D && D.repo);
  $("date").textContent = D.report_date || "";
  $("sub").textContent  = D.generated_at ? `Built ${D.generated_at}` : "";
  $("wx").innerHTML = weatherStrip(D.weather);
  const hidden = new Set(D.hidden_sections || []);
  $("panels").innerHTML =
    (D.treasury ? treasuryPanel(D.treasury, D.hkma_bars||[]) : balancePanel(D.hkma, D.hkma_bars||[]))
    + (hidden.has("Talking points") ? "" : talkingSection(D.talking_points))
    + ratePanel(D.rates);

  const S = D.sections || {}, L = D.labels || {};
  const block = (title, colour, groups) => {
    if(hidden.has(title)) return "";
    const total = groups.reduce((n,g) => n + (g.items||[]).length, 0);
    const body = groups.map(g => {
      if(!(g.items||[]).length) return "";
      return (g.sub ? `<div class="sub2">${esc(g.sub)}</div>` : "") +
        g.items.map(g.card || (g.work ? workCard : plainCard)).join("");
    }).join("") || `<div class="empty">Nothing met the bar today.</div>`;
    return `<section class="section">
      <div class="shead"><span class="dot" style="background:${colour}"></span>
        <h2>${esc(title)}</h2><span class="scount">${total} item${total===1?"":"s"}</span></div>
      ${body}</section>`;
  };

  $("sections").innerHTML =
    block("Work", "var(--work)", [{items:S.work||[], work:true}]) +
    block("Small Talk", "var(--talk)", [
      {sub:"Hong Kong", items:S.smalltalk_hk||[], card:it => plainCard(it, "Small Talk")},
      {sub:"Singapore", items:S.smalltalk_sg||[], card:it => plainCard(it, "Small Talk")}]) +
    block("Personal", "var(--life)", [
      {sub:"香港 · 民生", items:S.personal_hk||[], card:it => plainCard(it, "Personal")},
      {sub:"Singapore · Government", items:S.personal_sg||[], card:it => plainCard(it, "Personal")}]) +
    block("Juicy", "var(--juicy)", [
      {sub:"香港", items:S.juicy_hk||[], card:juicyCard},
      {sub:"Singapore", items:S.juicy_sg||[], card:juicyCard}]);

  // staleness + degraded build
  const msgs = [];
  if(D.generated_iso){
    const built = hkDay(new Date(D.generated_iso)), today = hkDay(new Date());
    if(built !== today){
      const days = Math.round((new Date(today) - new Date(built))/864e5);
      msgs.push(`Last built ${built}, ${days} day${days===1?"":"s"} ago. Check the Actions tab.`);
    }
  }
  if(D.treasury && D.treasury.balance && D.treasury.balance.stale){
    const asOf = D.treasury.balance.as_of ? ` (${D.treasury.balance.as_of})` : "";
    msgs.push(`HKMA figures are stale${asOf}. This run kept the last good values.`);
  }
  if(D.treasury && D.treasury.balance && D.treasury.balance.available === false){
    msgs.push("HKMA figures are unavailable, and there was no saved print to fall back on.");
  }
  if(D.build && (D.build.method === "fallback" || D.build.method === "rss-only")){
    msgs.push("Summarisation did not run. Cards below are headline-level only.");
  }
  if(msgs.length){ $("stale").innerHTML = msgs.join("<br>"); $("stale").classList.add("show"); }

  const rules = Array.isArray(D.mutes) ? D.mutes : [];
  const items = rules.map(r => `<li>${esc(r.summary || r.section || "")}</li>`).join("");
  $("foot").innerHTML =
    `<details class="mutes"><summary>Muted (${rules.length})</summary>`
    + (rules.length
        ? `<ul>${items}</ul>`
        : `<p class="mutes-empty">Nothing muted yet. Use ✕ Not for me on a card.</p>`)
    + `<p class="mutes-hint">Saved in data/mute_rules.json. Deleting the issue does not unmute; remove the rule from that file too.</p></details>`
    + `<div class="foot-note">Items flagged headline-only have no retrieved body text. `
    + `Open the source before repeating anything that matters.</div>`;
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
