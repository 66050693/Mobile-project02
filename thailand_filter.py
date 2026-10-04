"""รายชื่อรุ่นที่ขายอย่างเป็นทางการในไทย และการจับคู่ชื่อรุ่นระหว่างแหล่งข้อมูล

ชื่อเดียวกันอาจเขียนต่างกัน เช่น "Galaxy S26+" / "SAMSUNG Galaxy S26 Plus 5G" / "Samsung Galaxy S26 (12GB RAM + 512GB)"
จึงแปลงเป็น "คีย์รุ่น" มาตรฐานก่อนเทียบ: ตัดชื่อแบรนด์ ตัด 4G/5G ตัดวงเล็บรุ่นย่อย แปลง + เป็น plus
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

from config import CATALOG_PATH

# แบรนด์ย่อยจัดอยู่ในตระกูลเดียวกัน (Redmi/POCO เป็นของ Xiaomi, iQOO เป็นของ vivo)
BRAND_FAMILY = {"redmi": "xiaomi", "poco": "xiaomi", "xiaomi": "xiaomi", "iqoo": "vivo", "vivo": "vivo",
                "apple": "apple", "samsung": "samsung", "oppo": "oppo", "oneplus": "oneplus", "realme": "realme"}
SUB_BRANDS = {"redmi", "poco", "iqoo"}  # เป็นส่วนหนึ่งของชื่อรุ่น ห้ามตัดออก
MAIN_BRANDS = {"apple", "samsung", "xiaomi", "oppo", "vivo", "oneplus", "realme", "google", "motorola", "honor",
               "infinix", "tecno", "nothing", "huawei"}


@lru_cache(maxsize=1)
def load_catalog() -> dict:
    with CATALOG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def catalog_models() -> list[tuple[str, str]]:
    """[(แบรนด์, รุ่น), ...] ตามลำดับในไฟล์"""
    return [(b, m) for b, models in load_catalog().get("models", {}).items() for m in models]


def norm(text) -> str:
    s = str(text or "").lower().replace("®", "").replace("™", "")
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def family(brand: str) -> str:
    b = norm(brand)
    return BRAND_FAMILY.get(b, b)


def variant_label(name: str) -> str:
    """ข้อความในวงเล็บท้ายชื่อ เช่น '(12GB RAM + 512GB)' → '12GB RAM + 512GB'"""
    m = re.search(r"\(([^)]*)\)\s*$", str(name or ""))
    return m.group(1).strip() if m else ""


def model_key(name: str, brand: str = "") -> str:
    """คีย์รุ่นมาตรฐานสำหรับจับคู่ เช่น 'SAMSUNG Galaxy S26 Plus 5G (12GB RAM + 256GB)' → 'galaxy s26 plus'"""
    s = norm(re.sub(r"\([^)]*\)", " ", str(name or "")))
    s = s.replace("+", " plus ")
    for b in sorted((MAIN_BRANDS | {norm(brand)}) - SUB_BRANDS - {""}, key=len, reverse=True):
        if s.startswith(b + " "):
            s = s[len(b) + 1:]
            break
    s = re.sub(r"\b[45]g\b", " ", s)
    s = re.sub(r"(\w)\s+(pro|plus|max|ultra|mini|lite)\b", r"\1 \2", s)
    return re.sub(r"\s+", " ", s).strip()


@lru_cache(maxsize=1)
def thai_lookup() -> dict[tuple[str, str], tuple[str, str]]:
    """{(ตระกูลแบรนด์, คีย์รุ่น): (แบรนด์, ชื่อรุ่นตามรายชื่อไทย)}"""
    return {(family(b), model_key(m, b)): (b, m) for b, m in catalog_models()}


def match_thai(brand: str, name: str) -> tuple[str, str] | None:
    """ถ้ารุ่นนี้อยู่ในรายชื่อขายในไทย คืน (แบรนด์, ชื่อรุ่นไทย) ไม่งั้นคืน None"""
    return thai_lookup().get((family(brand), model_key(name, brand)))
