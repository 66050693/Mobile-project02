"""ค่าตั้งต้นและการอ่าน secrets ที่ใช้ร่วมกันทั้งโปรเจกต์"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
DATASET_PATH = DATA_DIR / "smartphones_2026.csv"      # Kaggle: Smartprix smartphones (April 2026) ราคาอินเดีย (INR)
PRICES_PATH = DATA_DIR / "prices.csv"                  # ราคาไทยที่ตรวจเอง (ทับราคาประมาณ)
MANUAL_SPECS_PATH = DATA_DIR / "specs_manual.csv"      # สเปกที่เติมเอง (ทับค่าใน dataset)
IMAGES_PATH = DATA_DIR / "images.csv"                  # ลิงก์รูปมือถือ (กรอกเอง)
CATALOG_PATH = ROOT / "thailand_catalog.json"          # รายชื่อรุ่นที่ขายอย่างเป็นทางการในไทย

DATASET_NAME = "Smartprix Smartphones (April 2026) — Kaggle"
DEFAULT_INR_TO_THB = 0.37   # อัตราแลกเปลี่ยนตั้งต้น ปรับได้ในแอป (ตรวจอัตราจริงก่อนใช้)
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"   # เปลี่ยนได้ด้วย GROQ_MODEL เช่น llama-3.3-70b-versatile
TOP_N = 5

_PLACEHOLDER_PREFIXES = ("ใส่_", "YOUR_")


def secret(name: str, default: str = "") -> str:
    """อ่านจาก Streamlit Secrets ก่อน แล้วค่อย environment (.env) ค่าตัวอย่างใน .env.example ถือว่าไม่ได้ตั้ง"""
    value = None
    try:
        import streamlit as st
        value = st.secrets.get(name)
    except Exception:
        pass
    value = str(value or os.getenv(name, default)).strip()
    return "" if value.startswith(_PLACEHOLDER_PREFIXES) else value


def flag(name: str) -> bool:
    return secret(name).lower() in {"1", "true", "yes"}
