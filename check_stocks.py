#!/usr/bin/env python3
"""
Stock Drop Alert -> LINE Messaging API
----------------------------------------
เช็คราคาหุ้น (ไทย + สหรัฐฯ) เทียบกับราคาปิดของวันก่อนหน้า
ถ้าร่วงเกิน threshold ที่กำหนด จะส่งข้อความแจ้งเตือนเข้า LINE
ผ่าน LINE Official Account (Messaging API - Broadcast)

ตั้งค่าหุ้นและ threshold ได้ที่ไฟล์ stocks.json
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests
import yfinance as yf

STATE_FILE = "state.json"
CONFIG_FILE = "stocks.json"

LINE_CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"


def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def today_key():
    # ใช้วันที่ (UTC) เป็น key เพื่อรีเซ็ตการแจ้งเตือนทุกวัน
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
    payload = {
        "messages": [{"type": "text", "text": message}]
    }
    resp = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"!! ส่ง LINE ไม่สำเร็จ ({resp.status_code}): {resp.text}")
    else:
        print("ส่งแจ้งเตือน LINE สำเร็จ")


def check_stock(ticker: str, threshold_pct: float):
    """คืนค่า (drop_pct, current_price, prev_close) หรือ None ถ้าดึงข้อมูลไม่ได้"""
    try:
        t = yf.Ticker(ticker)
        fast = t.fast_info
        current = fast.get("lastPrice") or fast.get("last_price")
        prev_close = fast.get("previousClose") or fast.get("previous_close")
        if current is None or prev_close is None or prev_close == 0:
            return None
        change_pct = (current - prev_close) / prev_close * 100
        return change_pct, current, prev_close
    except Exception as e:
        print(f"เช็ค {ticker} ไม่สำเร็จ: {e}")
        return None


def main():
    config = load_json(CONFIG_FILE, {"threshold_pct": 3.0, "tickers": []})
    threshold_pct = float(config.get("threshold_pct", 3.0))
    tickers = config.get("tickers", [])

    if not tickers:
        print("ไม่มีรายชื่อหุ้นใน stocks.json")
        return

    state = load_json(STATE_FILE, {})
    key = today_key()
    alerted_today = set(state.get(key, []))

    triggered_messages = []

    for ticker in tickers:
        result = check_stock(ticker, threshold_pct)
        if result is None:
            continue
        change_pct, current, prev_close = result
        print(f"{ticker}: {change_pct:+.2f}% (ปัจจุบัน {current}, ปิดก่อนหน้า {prev_close})")

        if abs(change_pct) >= threshold_pct and ticker not in alerted_today:
            triggered_messages.append(
                f"📉 {ticker} ร่วง {change_pct:.2f}%\n"
                f"ราคาปัจจุบัน: {current}\n"
                f"ราคาปิดก่อนหน้า: {prev_close}"
            )
            alerted_today.add(ticker)

    if triggered_messages:
        full_message = "แจ้งเตือนหุ้นร่วง 🔔\n\n" + "\n\n".join(triggered_messages)
        send_line_broadcast(full_message)
    else:
        print("ไม่มีหุ้นที่ร่วงเกิน threshold ในรอบนี้")

    # เก็บ state ไว้กันแจ้งเตือนซ้ำในวันเดียวกัน (ล้าง key เก่าทิ้งด้วย)
    state = {key: sorted(alerted_today)}
    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
