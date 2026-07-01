#!/usr/bin/env python3
"""
Stock Drop Alert + Momentum Signal -> LINE Messaging API
----------------------------------------------------------
1) เช็คราคาหุ้น (ไทย + สหรัฐฯ) เทียบกับราคาปิดของวันก่อนหน้า
   ถ้าร่วงเกิน threshold ที่กำหนด จะส่งข้อความแจ้งเตือน
2) เช็คสัญญาณ "โมเมนตัม" (ราคาขึ้นแรง + ปริมาณซื้อขายพุ่งผิดปกติ
   เทียบค่าเฉลี่ย 20 วัน) เพื่อโชว์เป็นข้อมูลประกอบการตัดสินใจ
3) **อัปเดตใหม่**: ส่งสรุปราคาหุ้นทุกตัวทุกรอบที่ทำงาน (ทุก 15 นาที) 
   ไม่ว่าจะเข้าเงื่อนไขแจ้งเตือนหรือไม่ก็ตาม

ตั้งค่าหุ้นและเงื่อนไขได้ที่ไฟล์ stocks.json
"""

import json
import os
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
    payload = {"messages": [{"type": "text", "text": message}]}
    resp = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)
    if resp.status_code != 200:
        print(f"!! ส่ง LINE ไม่สำเร็จ ({resp.status_code}): {resp.text}")
    else:
        print("ส่งแจ้งเตือน LINE สำเร็จ")


def check_stock(ticker: str, threshold_pct: float):
    """คืนค่า (change_pct, current_price, prev_close) หรือ None ถ้าดึงข้อมูลไม่ได้"""
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


def check_momentum(ticker: str, price_threshold_pct: float, volume_multiplier: float):
    """
    เช็คสัญญาณโมเมนตัม: ราคาขึ้น >= price_threshold_pct
    และปริมาณซื้อขายวันนี้ >= ค่าเฉลี่ย 20 วัน * volume_multiplier
    คืนค่า dict ข้อมูล หรือ None ถ้าไม่เข้าเงื่อนไข/ดึงข้อมูลไม่ได้
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1mo")
        if hist.empty or len(hist) < 5:
            return None

        today_row = hist.iloc[-1]
        prev_close = hist.iloc[-2]["Close"] if len(hist) >= 2 else today_row["Open"]
        current_price = today_row["Close"]
        today_volume = today_row["Volume"]

        # ค่าเฉลี่ยปริมาณ 20 วัน (ไม่รวมวันนี้)
        avg_volume = hist.iloc[:-1]["Volume"].tail(20).mean()
        if avg_volume == 0 or prev_close == 0:
            return None

        price_change_pct = (current_price - prev_close) / prev_close * 100
        volume_ratio = today_volume / avg_volume

        if price_change_pct >= price_threshold_pct and volume_ratio >= volume_multiplier:
            return {
                "ticker": ticker,
                "price_change_pct": price_change_pct,
                "current_price": current_price,
                "volume_ratio": volume_ratio,
                "today_volume": int(today_volume),
                "avg_volume": int(avg_volume),
            }
        return None
    except Exception as e:
        print(f"เช็คโมเมนตัม {ticker} ไม่สำเร็จ: {e}")
        return None


def main():
    config = load_json(
        CONFIG_FILE,
        {
            "threshold_pct": 3.0,
            "momentum_price_pct": 2.0,
            "momentum_volume_multiplier": 0.5,
            "tickers": [],
        },
    )
    drop_threshold_pct = float(config.get("threshold_pct", 3.0))
    momentum_price_pct = float(config.get("momentum_price_pct", 2.0))
    momentum_volume_multiplier = float(config.get("momentum_volume_multiplier", 0.5))
    tickers = config.get("tickers", [])

    if not tickers:
        print("ไม่มีรายชื่อหุ้นใน stocks.json")
        return

    state = load_json(STATE_FILE, {})
    key = today_key()
    alerted_today = set(state.get(f"{key}:drop", state.get(key, [])))
    momentum_alerted_today = set(state.get(f"{key}:momentum", []))

    drop_messages = []
    momentum_messages = []
    summary_messages = []  # เก็บข้อมูลราคารอบปกติของหุ้นทุกตัว

    for ticker in tickers:
        # --- เช็คราคาและอัปเดตข้อมูลสรุปประจำรอบ ---
        result = check_stock(ticker, drop_threshold_pct)
        if result is not None:
            change_pct, current, prev_close = result
            print(f"{ticker}: {change_pct:+.2f}% (ปัจจุบัน {current}, ปิดก่อนหน้า {prev_close})")

            # จัดอีโมจิหน้าชื่อหุ้นตามทิศทางราคาเพื่อความสวยงามและอ่านง่าย
            emoji = "🟢" if change_pct > 0 else "🔴" if change_pct < 0 else "⚪"
            summary_messages.append(f"{emoji} {ticker}: {current} ({change_pct:+.2f}%)")

            # เงื่อนไขแจ้งเตือนหุ้นร่วงรุนแรง (แจ้งเตือนครั้งเดียวต่อวันต่อบริษัท)
            if change_pct <= -drop_threshold_pct and ticker not in alerted_today:
                drop_messages.append(
                    f"📉 {ticker} ร่วง {change_pct:.2f}%\n"
                    f"ราคาปัจจุบัน: {current}\n"
                    f"ราคาปิดก่อนหน้า: {prev_close}"
                )
                alerted_today.add(ticker)
        else:
            summary_messages.append(f"⚠️ {ticker}: ดึงข้อมูลไม่สำเร็จ")

        # --- เช็คสัญญาณโมเมนตัม (ราคา+วอลุ่มพุ่ง) ---
        momentum = check_momentum(ticker, momentum_price_pct, momentum_volume_multiplier)
        if momentum is not None and ticker not in momentum_alerted_today:
            momentum_messages.append(
                f"🚀 {momentum['ticker']} ราคา +{momentum['price_change_pct']:.2f}%\n"
                f"ราคาปัจจุบัน: {momentum['current_price']:.2f}\n"
                f"ปริมาณซื้อขายวันนี้: {momentum['today_volume']:,} "
                f"(เฉลี่ย 20 วัน: {momentum['avg_volume']:,}, "
                f"คิดเป็น {momentum['volume_ratio']:.1f} เท่า)"
            )
            momentum_alerted_today.add(ticker)

    # --- 1. ส่งสรุปราคาหุ้นทุกตัวรอบปัจจุบัน (ส่งทุก 15 นาทีแน่นอน) ---
    if summary_messages:
        current_time_str = datetime.now().strftime("%H:%M")
        full_summary_message = f"📊 อัปเดตราคาหุ้นประจำรอบ ({current_time_str} น.)\n\n" + "\n".join(summary_messages)
        send_line_broadcast(full_summary_message)

    # --- 2. ส่งแจ้งเตือนด่วนกรณีหุ้นร่วงรุนแรง (ส่งเฉพาะเมื่อเข้าเงื่อนไขใหม่) ---
    if drop_messages:
        full_drop_message = "แจ้งเตือนหุ้นร่วงรุนแรง 🔔\n\n" + "\n\n".join(drop_messages)
        send_line_broadcast(full_drop_message)
    else:
        print("ไม่มีหุ้นที่ร่วงเกิน threshold ในรอบนี้")

    # --- 3. ส่งแจ้งเตือนกรณีโมเมนตัมพุ่ง (ส่งเฉพาะเมื่อเข้าเงื่อนไขใหม่) ---
    if momentum_messages:
        full_momentum_message = (
            "สัญญาณโมเมนตัมน่าจับตา 🚀\n"
            "(ราคา+ปริมาณซื้อขายพุ่งผิดปกติ เป็นข้อมูลสถิติ "
            "ไม่ใช่คำแนะนำให้ซื้อ โปรดวิเคราะห์เพิ่มเติมก่อนตัดสินใจ)\n\n"
            + "\n\n".join(momentum_messages)
        )
        send_line_broadcast(full_momentum_message)
    else:
        print("ไม่มีหุ้นที่เข้าเงื่อนไขโมเมนตัมในรอบนี้")

    # เก็บ state ไว้กันแจ้งเตือนซ้ำในวันเดียวกัน (ล้าง key เก่าทิ้งด้วย)
    state = {
        f"{key}:drop": sorted(alerted_today),
        f"{key}:momentum": sorted(momentum_alerted_today),
    }
    save_json(STATE_FILE, state)


if __name__ == "__main__":
    main()
