# รายงานข้อมูล v8 (ตรวจวันที่ 4 ต.ค. 2026)

## 1) images.csv
- เติมลิงก์รูปแล้ว **36 จาก 42 รุ่น** ทุกลิงก์เป็นไฟล์รูปตรงจากเว็บ/CDN ทางการของแบรนด์ (apple.com, images.samsung.com, i02.appmifile.com, oppo.com / opsg-imgcdn-sg.heytapimg.com)
- ทดสอบเปิดทุกลิงก์ในเบราว์เซอร์แล้ว: โหลดเป็นรูปได้ครบ 36/36
- **หาไม่พบ (เว้นว่าง):** Xiaomi 17T, POCO C81 Pro (หน้าเว็บทางการให้แค่โลโก้ ไม่ใช่รูปสินค้า), vivo X300, X300 Pro, X300 Ultra, X Fold5 (ไม่พบลิงก์รูปตรงจากเว็บ vivo ไทยที่ยืนยันได้)
- หมายเหตุ: รูป OPPO A7 Pro / A7 Pro Max มาจากหน้า oppo.com ต่างประเทศ (รุ่นยังไม่ขายในไทย)

## 2) prices.csv
- ไฟล์มี 1 แถวต่อรุ่น (ไม่มีคอลัมน์ความจุ) จึงใส่ **ราคาเริ่มต้น (ความจุเล็กสุด)** ใน price_thb และเขียนราคาความจุอื่นไว้ในคอลัมน์ source
- updated = 2026-10-04 ทุกแถวที่มีราคา
- ราคาตามที่แสดงบนเว็บวันที่ตรวจ อาจมีโปรโมชันชั่วคราว (ระบุไว้ใน source)

| แบรนด์ | แหล่งที่มา |
|---|---|
| Apple | apple.com/th/shop (ราคาปกติ) |
| Samsung | samsung.com/th หน้าซื้อ (ราคาปกติ ไม่รวม flash sale) |
| Xiaomi / POCO / REDMI | mi.com/th (ราคาที่แสดงตอนนี้ ราคาขีดฆ่าอยู่ใน source) |
| OPPO | oppo.com/th store และ bnn.in.th (BaNANA ร้านค้าทางการ) สำหรับ Find X9, X9 Pro, X8, X8 Pro |
| vivo X300 / X300 Pro | ราคาเปิดตัวไทย 27 พ.ย. 2025 (ข่าว mgronline อ้างงานเปิดตัว vivo) |

**ไม่มีราคา (เว้นว่าง):**
- OPPO Find N6: ไม่พบราคาบนเว็บทางการ/ร้านทางการในไทย
- OPPO A7 Pro 5G, A7 Pro Max 5G: เปิดตัวที่มาเลเซีย ในไทยมีแค่ผ่าน กสทช. ยังไม่วางขาย
- vivo X300 Ultra, X Fold5: ไม่พบราคาไทยที่ยืนยันได้จากแหล่งทางการ

**ราคาที่รุ่นย่อยยังไม่ชัด:**
- Xiaomi ทุกรุ่น: เว็บแสดงราคาเริ่มต้นแต่ไม่ระบุว่าเป็น RAM/ROM ไหน
- OPPO A6x: ราคาที่สอง 8,999 ไม่ชัดว่าเป็นราคาปกติหรือรุ่นย่อย
- Galaxy S26 Ultra 16/1TB: เว็บไม่แสดงราคา
- vivo X300 Pro 12/256 (36,999): มีแต่ในสื่อ ยังไม่ยืนยันจากทางการ จึงไม่ได้ใส่
- Find X8 / X8 Pro: สถานะ "เร็วๆ นี้" ที่ BaNANA

## 3) smartphones_2026.csv (997 แถว × 26 คอลัมน์)
คงหัวคอลัมน์ ลำดับคอลัมน์ และรูปแบบเดิม (TRUE/FALSE, ตัวเลข) แก้ไขไป 19 แถว:

| รุ่น | คอลัมน์ | เดิม → ใหม่ | เหตุผล |
|---|---|---|---|
| 7 รุ่นที่เป็น 1TB/2TB (S26 Ultra 1TB, S25 Ultra 1TB, iPhone 17 Pro Max 1TB/2TB, iPhone 15 Pro Max 1TB, OnePlus 13 1TB, Motorola Signature 1TB) | memory | 1→1024, 2→2048 | หน่วยต้องเป็น GB เหมือนแถวอื่น ไม่งั้นระบบอ่านเป็น 1GB |
| Apple iPhone 12 Pro Max | screen_size | 12 → 6.7 | สเปก Apple 6.7 นิ้ว |
| iPhone 16, 16 Plus, 16 (256GB), 16 Plus (256GB) | refresh_rate | ว่าง → 60 | สเปก Apple 60Hz |
| Apple iPhone Air | refresh_rate | ว่าง → 120 | ProMotion สูงสุด 120Hz |
| Oppo Find N6 | os | ว่าง → Android v16 | ColorOS 16 (Android 16) |
| 6 แถว | os | เช่น "Android v14.0"→"Android v14", "Android v9.0 (Pie)"→"Android v9", "Android 15 Go"→"Android v15 (Go)" | ให้รูปแบบตรงกับแถวอื่น |

**ผลตรวจอัตโนมัติทุกแถว:** ไม่มีแถวซ้ำและไม่มีชื่อรุ่นซ้ำ
- ค่าว่างที่เหลือ: num_core 17, processor_speed 135, fast_charging 56, charging_ratio 56, refresh_rate ~44, rear_camera 16, front_camera 18, os ~9, processor_brand 1
- ค่าเหล่านี้คงไว้ว่าง เพราะยืนยันไม่ได้

**ยืนยันไม่ได้ (คงค่าเดิม):**
- Apple iPhone 18e และ iPhone 17 Plus: ข้อมูลเลื่อนคอลัมน์ (แบต 6.2/6.8, จอ 48) น่าจะเป็นรุ่นข่าวลือ
- ชาร์จเร็วผิดปกติ: Motorola Edge 70 Ultra 11200W, Oppo Find X10 Pro Max 800W, Vivo Y31d 444W, Realme GT 10000mAh 320W (แอปตัดค่านอกช่วงให้อัตโนมัติอยู่แล้ว)
- processor_name เป็น "Octa Core Processor" (~50 แถว เช่น Reno16 / Reno16 Pro) และ processor_brand = "unknown" (36 แถว)
- Oppo Find X9s แบต 10000mAh และรุ่นที่ยังไม่เปิดตัวใน dataset (ข้อมูลจาก Smartprix)
- สเปกส่วนใหญ่ของ 997 แถวไม่ได้เทียบเว็บผู้ผลิตทีละค่า ตรวจเฉพาะรุ่นที่ขายในไทยแบบคัดกรองค่าที่ผิดชัดเจน
- dataset เป็นข้อมูลรุ่นอินเดีย สเปกไทยบางรุ่นอาจต่าง (เช่น แบต/ชิป) จึงไม่แก้

## 4) ความตรงกันของ 3 ไฟล์
- images.csv และ prices.csv มี 42 รุ่นตรงกับ thailand_catalog.json ครบทุกแถว
- จับคู่กับ dataset ได้ 20 รุ่น อีก 22 รุ่น (เช่น iPhone Duo/18 Pro, Fold8/Flip8, REDMI Note 17, POCO, Reno16 F, A6x ฯลฯ) ไม่มีใน dataset ระบบจะแสดงผ่านแคตตาล็อก/ราคาไทยตามเดิม
