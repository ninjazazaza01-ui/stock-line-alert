#!/usr/bin/env python3
"""
Stock News Digest -> LINE Messaging API
------------------------------------------
ดึงข่าวล่าสุดของหุ้นแต่ละตัวใน stocks.json (ข้อมูลข่าวจาก Yahoo Finance
ผ่าน yfinance ไม่ต้องขอ API key เพิ่ม) แล้วส่งสรุปเข้า LINE

ออกแบบให้รันวันละ 2 ครั้ง (เช้า/เย็น) ตาม cron schedule ในไฟล์ workflow
มีระบบกันข่าวซ้ำ - ถ้าข่าวเดิมถูกส่งไปแล้วในวันนั้น จะไม่ส่งซ้ำอีก
"""

import json
import os
from datetime import datetime, timezone, timedelta

import requests
import yfinance as yf

STATE_FILE = "state.json"
CONFIG_FILE = "stocks.json"

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"

MAX_MESSAGE_CHARS = 4500       # กันเกิน limit ข้อความของ LINE ต่อ 1 ข้อความ
NEWS_LOOKBACK_HOURS = 15       # ดึงเฉพาะข่าวที่เผยแพร่ในช่วงกี่ชั่วโมงที่ผ่านมา


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_key():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def send_line_broadcast(message: str):
    if not LINE_CHANNEL_ACCESS_TOKEN:
        print("!! ไม่พบ LINE_CHANNEL_ACCESS_TOKEN - ข้ามการส่งข้อความ (โหมดทดสอบ)")
        print("ข้อความที่จะส่ง:\n", message)
        return
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {LINE_CHANNEL_ACCESS_TOKEN}",
    }
    payload = {"messages": [{"type": "text", "text": message}]}
    resp = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"!! ส่ง LINE ไม่สำเร็จ ({resp.status_code}): {resp.text}")
    else:
        print("ส่งข่าวเข้า LINE สำเร็จ")


def extract_news_item(raw: dict):
    """yfinance คืนรูปแบบข่าวได้หลายเวอร์ชัน พยายามรองรับทั้งแบบเก่าและใหม่"""
    content = raw.get("content", raw)
    title = content.get("title") or raw.get("title")

    provider = content.get("provider")
    publisher = provider.get("displayName") if isinstance(provider, dict) else raw.get("publisher")

    canonical = content.get("canonicalUrl")
    link = canonical.get("url") if isinstance(canonical, dict) else raw.get("link")

    pub_ts = None
    pub_date = content.get("pubDate")
    if pub_date:
        try:
            pub_ts = datetime.strptime(pub_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except Exception:
            pub_ts = None
    if pub_ts is None and raw.get("providerPublishTime"):
        try:
            pub_ts = datetime.fromtimestamp(raw["providerPublishTime"], tz=timezone.utc)
        except Exception:
            pub_ts = None

    if not title or not link:
        return None
    return {"title": title, "publisher": publisher or "-", "link": link, "pub_ts": pub_ts}


def get_recent_news(ticker: str, lookback_hours: int, max_items: int):
    try:
        raw_items = yf.Ticker(ticker).news or []
    except Exception as e:
        print(f"ดึงข่าว {ticker} ไม่สำเร็จ: {e}")
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    parsed = []
    for raw in raw_items:
        item = extract_news_item(raw)
        if item is None:
            continue
        if item["pub_ts"] is not None and item["pub_ts"] < cutoff:
            continue
        parsed.append(item)

    parsed.sort(key=lambda x: x["pub_ts"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return parsed[:max_items]


def main():
    config = load_json(CONFIG_FILE, {"tickers": []})
    tickers = config.get("tickers", [])
    max_items_per_ticker = int(config.get("news_max_items_per_ticker", 1))

    if not tickers:
        print("ไม่มีรายชื่อหุ้นใน stocks.json")
        return

    state = load_json(STATE_FILE, {})
    key = today_key()
    sent_urls = set(state.get(f"{key}:news_urls", []))

    news_lines = []
    for ticker in tickers:
        items = get_recent_news(ticker, NEWS_LOOKBACK_HOURS, max_items_per_ticker)
        for item in items:
            if item["link"] in sent_urls:
                continue
            news_lines.append(f"📰 {ticker} | {item['publisher']}\n{item['title']}\n{item['link']}")
            sent_urls.add(item["link"])

    if not news_lines:
        print("ไม่มีข่าวใหม่ที่เข้าเงื่อนไขในรอบนี้")
    else:
        # แบ่งข้อความเป็นชุดๆ กันเกิน limit ต่อ 1 ข้อความของ LINE
        chunks = []
        current_chunk = "📰 สรุปข่าวหุ้นประจำวัน\n\n"
        for line in news_lines:
            candidate = current_chunk + line + "\n\n"
            if len(candidate) > MAX_MESSAGE_CHARS:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n\n"
            else:
                current_chunk = candidate
        if current_chunk.strip():
            chunks.append(current_chunk.strip())

        for chunk in chunks:
            send_line_broadcast(chunk)

    state[f"{key}:news_urls"] = sorted(sent_urls)
    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
