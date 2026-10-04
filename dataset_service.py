"""โหลดและเตรียมข้อมูลมือถือจาก dataset Kaggle (Smartprix, April 2026)

ขั้นตอน
1. อ่าน CSV → เปลี่ยนชื่อคอลัมน์เป็นมาตรฐาน
2. รวมรุ่นย่อย (เช่น 8/256 กับ 12/512) เป็น 1 รุ่น ใช้รุ่นเริ่มต้น (ราคาต่ำสุด) เป็นตัวแทน
3. จับคู่กับรายชื่อรุ่นที่ขายในไทย (thailand_catalog.json)
4. ราคา: ใช้ราคาไทยที่ตรวจเอง (data/prices.csv) ถ้ามี ไม่งั้นประมาณจากราคาอินเดีย × อัตราแลกเปลี่ยน
ไม่พึ่ง Streamlit เพื่อให้ทดสอบแยกได้
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATASET_PATH, IMAGES_PATH, MANUAL_SPECS_PATH, PRICES_PATH
from thailand_filter import catalog_models, family, match_thai, model_key, variant_label

COLUMN_MAP = {
    "brand_name": "brand_raw", "model": "name_raw", "price": "price_inr", "spec_score": "smartprix_score",
    "vfm_label": "vfm_label", "has_5G": "has_5g", "has_NFC": "has_nfc", "has_IR": "has_ir",
    "processor_name": "chipset", "ram": "ram_gb", "memory": "storage_gb", "battery_capacity(mAh)": "battery_mah",
    "fast_charging(W)": "charging_w", "screen_size": "display_in", "refresh_rate": "refresh_hz",
    "rear_camera": "camera_mp", "front_camera": "front_mp", "rear_camera_count": "rear_cams", "os": "os",
}
BRAND_DISPLAY = {"apple": "Apple", "samsung": "Samsung", "xiaomi": "Xiaomi", "poco": "POCO", "redmi": "Redmi",
                 "oppo": "OPPO", "vivo": "vivo", "iqoo": "iQOO", "oneplus": "OnePlus", "realme": "realme",
                 "honor": "HONOR", "google": "Google", "motorola": "Motorola", "nothing": "Nothing", "cmf": "CMF",
                 "infinix": "Infinix", "tecno": "TECNO", "huawei": "HUAWEI", "nubia": "nubia", "hmd": "HMD"}
SANE_RANGES = {"ram_gb": (1, 32), "storage_gb": (8, 2048), "battery_mah": (1000, 20000), "charging_w": (5, 300),
               "display_in": (3, 10), "refresh_hz": (30, 240), "camera_mp": (2, 250), "front_mp": (1, 100)}
NUMERIC = ["price_inr", "smartprix_score", "ram_gb", "storage_gb", "battery_mah", "charging_w", "display_in",
           "refresh_hz", "camera_mp", "front_mp", "rear_cams"]


# ---------------------------------------------------------------------------
# คะแนนชิป (ประมาณจากชื่อชิป ไม่ใช่ benchmark จริง ใช้จัดอันดับคร่าวๆ)
# ---------------------------------------------------------------------------
CHIP_RULES: list[tuple[str, float]] = [
    (r"snapdragon 8 ?elite|snapdragon 8 gen ?[45]|dimensity 9[4-9]\d\d|exynos 2[56]\d\d|xring|tensor g?[56]\b|kirin 90[3-9]\d", 95),
    (r"snapdragon 8 gen ?3|dimensity 93\d\d|tensor g4|kirin 90[0-2]\d", 88),
    (r"snapdragon 8s|snapdragon 8\+? gen ?[12]|snapdragon 7\+|dimensity 9[0-2]\d\d|dimensity 8[4-9]\d\d|exynos 2[24]\d\d|tensor g[23]", 78),
    (r"dimensity 8[0-3]\d\d|snapdragon 7s? gen ?[34]|exynos 1[5-6]\d\d|snapdragon 8(88|70|65)|exynos 2100", 66),
    (r"snapdragon 7|dimensity 7\d\d\d|dimensit 7\d\d\d|dimensity 1[0-3]\d\d|exynos 1[2-4]\d\d|helio g99|helio g1\d\d|snapdragon 85\d", 52),
    (r"snapdragon 6|dimensity 6\d\d\d|helio g[89]\d|exynos 8\d\d|snapdragon 73\d", 40),
    (r"snapdragon 4|helio|unisoc|tiger|t\d{3,4}\b", 28),
]


def chip_score(chipset) -> float | None:
    if chipset is None or (isinstance(chipset, float) and np.isnan(chipset)):
        return None
    c = re.sub(r"\s+", " ", str(chipset).lower()).strip()
    m = re.search(r"(?:apple|bionic) a(\d{2})|\ba(\d{2}) ?(?:pro|bionic)\b|^a(\d{2})$", c)
    if m:
        gen = int(next(g for g in m.groups() if g))
        return float(np.clip(95 - (19 - gen) * 5, 40, 100))
    for pattern, score in CHIP_RULES:
        if re.search(pattern, c):
            return score
    return None


# ---------------------------------------------------------------------------
# โหลด dataset
# ---------------------------------------------------------------------------
def _display_brand(raw: str) -> str:
    return BRAND_DISPLAY.get(str(raw).lower(), str(raw).title())


def _short_name(name: str, brand_raw: str) -> str:
    """ตัดชื่อแบรนด์และวงเล็บรุ่นย่อยออก เช่น 'SAMSUNG Galaxy S26 5G (12GB RAM + 512GB)' → 'Galaxy S26 5G'"""
    s = re.sub(r"\([^)]*\)\s*$", "", str(name)).strip()
    words = s.split(" ", 1)
    if len(words) == 2 and words[0].lower() in {str(brand_raw).lower(), "samsung", "apple", "xiaomi", "oppo", "vivo"}:
        s = words[1]
    return s


def load_dataset(path: Path = DATASET_PATH) -> pd.DataFrame:
    """1 แถวต่อรุ่น (รวมรุ่นย่อยแล้ว) พร้อมคอลัมน์มาตรฐาน"""
    raw = pd.read_csv(path)
    missing = [c for c in ("brand_name", "model", "price") if c not in raw.columns]
    if missing:
        raise ValueError(f"ไฟล์ dataset ขาดคอลัมน์ {missing}")
    df = raw.rename(columns=COLUMN_MAP)[[c for c in COLUMN_MAP.values() if c in raw.rename(columns=COLUMN_MAP).columns]]
    for col in NUMERIC:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ("has_5g", "has_nfc", "has_ir"):
        if col in df:
            df[col] = df[col].astype(str).str.lower().isin({"true", "1", "yes"})
    df = df[df["price_inr"] > 0].copy()
    # ค่าที่เป็นไปไม่ได้ทางกายภาพ (พิมพ์ผิดใน dataset) ให้ถือว่าไม่มีข้อมูล
    for col, (lo, hi) in SANE_RANGES.items():
        if col in df:
            df.loc[~df[col].between(lo, hi), col] = np.nan

    df["family"] = df["brand_raw"].map(family)
    df["key"] = [model_key(n, b) for n, b in zip(df["name_raw"], df["brand_raw"])]
    df["variant"] = df["name_raw"].map(variant_label)

    # รวมรุ่นย่อย: เลือกรุ่นที่ถูกที่สุดเป็นตัวแทน เก็บช่วงราคาและความจุสูงสุดไว้
    df = df.sort_values(["family", "key", "price_inr"])
    agg = df.groupby(["family", "key"]).agg(variants=("name_raw", "size"), price_inr_max=("price_inr", "max"),
                                            storage_max=("storage_gb", "max"), ram_max=("ram_gb", "max"))
    base = df.drop_duplicates(["family", "key"], keep="first").set_index(["family", "key"]).join(agg).reset_index()

    base["brand"] = base["brand_raw"].map(_display_brand)
    base["model"] = [_short_name(n, b) for n, b in zip(base["name_raw"], base["brand_raw"])]
    thai = [match_thai(b, n) for b, n in zip(base["brand_raw"], base["name_raw"])]
    base["in_thailand"] = [t is not None for t in thai]
    base["thai_name"] = [t[1] if t else None for t in thai]
    base.loc[base["in_thailand"], "model"] = base.loc[base["in_thailand"], "thai_name"]
    base.loc[base["in_thailand"], "brand"] = [t[0] for t in thai if t]
    base["perf_score"] = base["chipset"].map(chip_score)
    base["name"] = [m if m.lower().startswith(b.lower() + " ") else f"{b} {m}" for b, m in zip(base["brand"], base["model"])]
    return base.drop_duplicates("name").reset_index(drop=True)


def apply_manual_specs(df: pd.DataFrame, path: Path = MANUAL_SPECS_PATH) -> pd.DataFrame:
    """ทับสเปกด้วยค่าที่กรอกเองใน data/specs_manual.csv (เฉพาะช่องที่กรอก)"""
    if not path.exists():
        return df
    manual = pd.read_csv(path, encoding="utf-8-sig")
    if manual.empty:
        return df
    out = df.copy()
    keys = {(family(b), model_key(m, b)): i for i, (b, m) in enumerate(zip(out["brand"], out["model"]))}
    for _, row in manual.iterrows():
        i = keys.get((family(row.get("brand", "")), model_key(row.get("model", ""), row.get("brand", ""))))
        if i is None:
            continue
        for col, value in row.items():
            if col in out.columns and col not in ("brand", "model") and pd.notna(value) and str(value).strip():
                out.at[out.index[i], col] = value
    out["perf_score"] = [p if pd.notna(p) else chip_score(c) for p, c in zip(out["perf_score"], out["chipset"])]
    return out


# ---------------------------------------------------------------------------
# ราคา
# ---------------------------------------------------------------------------
def empty_prices() -> pd.DataFrame:
    models = catalog_models()
    return pd.DataFrame({"brand": [b for b, _ in models], "model": [m for _, m in models],
                         "price_thb": np.nan, "updated": "", "source": ""})


def load_prices(path: Path = PRICES_PATH) -> pd.DataFrame:
    if not path.exists():
        return empty_prices()
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    for col in ("brand", "model", "price_thb", "updated", "source"):
        if col not in df:
            df[col] = ""
    df["price_thb"] = pd.to_numeric(df["price_thb"].str.replace(r"[,฿\s]", "", regex=True), errors="coerce")
    return df[["brand", "model", "price_thb", "updated", "source"]]


def apply_prices(df: pd.DataFrame, prices: pd.DataFrame, inr_to_thb: float) -> pd.DataFrame:
    """price_thb = ราคาไทยที่ตรวจเอง ถ้าไม่มีใช้ราคาอินเดีย × อัตราแลกเปลี่ยน (price_kind บอกที่มา)"""
    out = df.copy()
    p = prices.dropna(subset=["price_thb"]).copy()
    p["k"] = [(family(b), model_key(m, b)) for b, m in zip(p["brand"], p["model"])]
    p = p.drop_duplicates("k", keep="last").set_index("k")
    keys = pd.Series([(family(b), model_key(m, b)) for b, m in zip(out["brand"], out["model"])], index=out.index)
    thai_price = keys.map(p["price_thb"]) if len(p) else pd.Series(np.nan, index=out.index)
    out["price_est"] = (out["price_inr"] * float(inr_to_thb)).round(-1)
    out["price_thb"] = thai_price.fillna(out["price_est"])
    out["price_kind"] = np.where(thai_price.notna(), "ราคาไทย", "ประมาณจากราคาอินเดีย")
    out["price_updated"] = keys.map(p["updated"]).fillna("") if len(p) else ""
    out["price_source"] = keys.map(p["source"]).fillna("") if len(p) else ""
    return out


def prices_csv(df: pd.DataFrame) -> bytes:
    cols = ["brand", "model", "price_thb", "updated", "source"]
    return ("﻿" + df[cols].to_csv(index=False)).encode("utf-8")


def coverage(df: pd.DataFrame) -> dict:
    thai = df[df["in_thailand"]]
    return {"dataset_models": len(df), "catalog_models": len(catalog_models()), "thai_matched": len(thai),
            "thai_priced": int((thai["price_kind"] == "ราคาไทย").sum()) if "price_kind" in thai else 0,
            "missing": sorted(set(m for _, m in catalog_models()) - set(thai["model"]))}


def apply_images(df: pd.DataFrame, path: Path = IMAGES_PATH) -> pd.DataFrame:
    """เพิ่มคอลัมน์ image (ลิงก์รูป) จาก data/images.csv รุ่นที่ไม่มีรูปเป็นค่าว่าง"""
    out = df.copy()
    out["image"] = ""
    if not path.exists():
        return out
    img = pd.read_csv(path, encoding="utf-8-sig", dtype=str).fillna("")
    img = img[img["image_url"].str.startswith("http")]
    lookup = {(family(b), model_key(m, b)): u for b, m, u in zip(img["brand"], img["model"], img["image_url"])}
    out["image"] = [lookup.get((family(b), model_key(m, b)), "") for b, m in zip(out["brand"], out["model"])]
    return out
