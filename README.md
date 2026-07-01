# แจ้งเตือนหุ้นร่วงผ่าน LINE (ฟรี, รันบน GitHub Actions)

ระบบนี้จะเช็คราคาหุ้นไทยและสหรัฐฯ ทุก 15 นาทีในช่วงเวลาตลาดเปิด
ถ้าหุ้นตัวไหนร่วงเกิน % ที่กำหนด จะส่งข้อความแจ้งเตือนเข้า LINE
ของคุณโดยอัตโนมัติ ผ่าน LINE Messaging API (ฟรี ไม่มีค่าใช้จ่าย
ในปริมาณการใช้งานระดับส่วนตัว)

---

## ขั้นตอนที่ 1: สร้าง LINE Official Account + เอา Channel Access Token

1. ไปที่ https://developers.line.biz/console/ แล้ว login ด้วยบัญชี LINE ของคุณ
2. สร้าง **Provider** ใหม่ (ตั้งชื่ออะไรก็ได้ เช่น "MyAlerts")
3. ในหน้า Provider กด **Create a new channel** เลือก **Messaging API**
4. กรอกข้อมูล (ชื่อ, หมวดหมู่, อีเมล ฯลฯ) แล้วกดสร้าง
5. เข้าไปที่ช่อง (channel) ที่สร้างเสร็จ ไปแท็บ **Messaging API**
   - ปิด (Disable) "Auto-reply messages" และ "Greeting messages" ได้ถ้าไม่อยากให้บอทตอบกลับอัตโนมัติ
   - เลื่อนหาช่อง **Channel access token (long-lived)** กด **Issue** เพื่อออก token
   - **คัดลอก token นี้เก็บไว้** (จะใช้ในขั้นตอนที่ 3)
6. สแกน **QR Code** ของ Official Account ตัวนี้ด้วยแอป LINE ในมือถือคุณ
   เพื่อเพิ่มเป็นเพื่อน (ต้องเป็นเพื่อนก่อน ถึงจะรับ broadcast message ได้)

---

## ขั้นตอนที่ 2: สร้าง GitHub repository

1. สร้าง repo ใหม่บน GitHub (public หรือ private ก็ได้ — public จะไม่เสีย
   Actions minutes เลย, private จะมีโควต้าฟรีให้ระดับหนึ่งต่อเดือน)
2. อัปโหลดไฟล์ทั้งหมดในโฟลเดอร์นี้ขึ้น repo (`check_stocks.py`,
   `stocks.json`, `requirements.txt`, `.github/workflows/stock-alert.yml`)

---

## ขั้นตอนที่ 3: ใส่ Channel Access Token เป็น GitHub Secret

1. ใน repo ไปที่ **Settings → Secrets and variables → Actions**
2. กด **New repository secret**
   - Name: `LINE_CHANNEL_ACCESS_TOKEN`
   - Value: (วาง token ที่คัดลอกไว้จากขั้นตอนที่ 1)
3. กด **Add secret**

---

## ขั้นตอนที่ 4: ปรับรายชื่อหุ้นและ % ที่ต้องการแจ้งเตือน

แก้ไขไฟล์ `stocks.json`:

```json
{
  "threshold_pct": 3.0,
  "tickers": ["PTT.BK", "AOT.BK", "CPALL.BK", "AAPL", "TSLA", "NVDA"]
}
```

- `threshold_pct` คือ % ที่ร่วงจากราคาปิดวันก่อนหน้า ถึงจะแจ้งเตือน (ตัวอย่าง = ร่วงตั้งแต่ 3% ขึ้นไป)
- หุ้นไทยในตลาด SET ให้ใส่ต่อท้ายด้วย `.BK` เช่น `PTT.BK`, `SCB.BK`, `DELTA.BK`
- หุ้นสหรัฐฯ ใส่ชื่อ ticker ปกติ เช่น `AAPL`, `TSLA`, `NVDA`
- ดูชื่อ ticker ที่ถูกต้องได้จาก https://finance.yahoo.com

---

## ขั้นตอนที่ 5: ทดสอบรัน

1. ไปที่แท็บ **Actions** ใน repo
2. เลือก workflow "Stock Drop Alert"
3. กด **Run workflow** เพื่อรันทันที (ไม่ต้องรอ schedule)
4. เช็ค log ว่ารันผ่านหรือไม่ ถ้ามีหุ้นร่วงเกิน threshold ตอนนี้ ควรมีข้อความ
   เด้งเข้า LINE ของคุณ

หลังจากนี้ระบบจะรันอัตโนมัติทุก 15 นาทีตามเวลาที่ตั้งไว้ในไฟล์ workflow
(ครอบคลุมเวลาตลาดหุ้นไทยและสหรัฐฯ) โดยไม่ต้องทำอะไรเพิ่ม

---

## หมายเหตุ

- ข้อความแจ้งเตือนจะถูกส่งแค่ **1 ครั้งต่อหุ้นต่อวัน** (กันไม่ให้สแปม) โดยระบบ
  จะรีเซ็ตนับใหม่ทุกวัน ผ่านไฟล์ `state.json` ที่ commit กลับเข้า repo อัตโนมัติ
- LINE Messaging API แบบ Broadcast จะส่งข้อความไปหา **ทุกคนที่แอด OA นี้เป็นเพื่อน**
  ถ้าใช้ส่วนตัว ก็แค่แอดตัวเองเป็นเพื่อนคนเดียวก็พอ
- ราคาหุ้นดึงจาก Yahoo Finance (yfinance) ซึ่งอาจดีเลย์เล็กน้อย (ไม่ใช่ real-time
  แบบ tick-by-tick) เหมาะกับการแจ้งเตือนทั่วไป แต่ไม่เหมาะกับการเทรดแบบ high-frequency
- ถ้าอยากให้เช็คถี่กว่า 15 นาที ปรับ cron ในไฟล์ `.github/workflows/stock-alert.yml`
  ได้ (แต่ GitHub จำกัดความถี่ต่ำสุดของ schedule ไว้ที่ประมาณ 5 นาที)
