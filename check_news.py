#!/usr/bin/env python3
"""
Stock News Digest (Bullish Filters) -> LINE Messaging API
----------------------------------------------------------
1) ดึงข่าวล่าสุดจาก Yahoo Finance (ต่างประเทศ) ผ่าน yfinance
2) กรองเฉพาะข่าวเชิงบวก: หุ้นพุ่ง, ดีลยักษ์ใหญ่, โปรเจกต์ที่จะทำให้อนาคตเติบโต
3) สรุปใจความแบบสั้น กระชับ พร้อมระบุชื่อหุ้นที่คาดว่าจะพุ่งชัดเจน
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

# คำสำคัญ (Keywords) ข่าวเชิงบวก/ดีลใหญ่/หุ้นพุ่ง
BULLISH_KEYWORDS = [
    "surge", "soar", "jump", "rally", "spike", "skyrocket", "leap", "gain", "bullish",
    "deal", "acquisition", "merger", "partnership", "buyout", "mega", "billion",
    "growth", "unveil", "launch", "expand", "breakthrough", "beat", "positive"
]


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


def is_bullish_news(title: str) -> bool:
    """ตรวจสอบว่าหัวข้อข่าวมีคำสำคัญเชิงบวกหรือดีลใหญ่หรือไม่"""
    title_lower = title.lower()
    return any(keyword in title_lower for keyword in BULLISH_KEYWORDS)


def extract_news_item(raw: dict):
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
        
        # คัดกรองเอาเฉพาะข่าวแนวโน้มพุ่ง/ดีลใหญ่
        if not is_bullish_news(item["title"]):
            continue
            
        parsed.append(item)

    parsed.sort(key=lambda x: x["pub_ts"] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return parsed[:max_items]


def main():
    config = load_json(CONFIG_FILE, {"tickers": []})
    tickers = config.get("tickers", [])
    max_items_per_ticker = int(config.get("news_max_items_per_ticker", 2)) # เพิ่มโอกาสให้เจอข่าวหลังกรอง

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
            
            # ปรับรูปแบบข่าวย่อ เน้นความกระชับและระบุหุ้นที่จะพุ่งชัดเจน
            news_format = (
                f"🔥 หุ้นน่าจับตา: {ticker}\n"
                f"📢 สรุปข่าว: {item['title']}\n"
                f"🌐 ลิงก์ข่าวต่างประเทศ: {item['link']}"
            )
            news_lines.append(news_format)
            sent_urls.add(item["link"])

    if not news_lines:
        print("ไม่มีข่าวหุ้นพุ่งหรือดีลใหญ่ในรอบนี้")
    else:
        chunks = []
        current_chunk = "🚀 เจาะข่าวเด่น หุ้นส่อแววพุ่ง! 📈\n\n"
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
