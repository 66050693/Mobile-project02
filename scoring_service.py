"""จัดอันดับมือถือตามงบและการใช้งาน (สูตรคะแนนที่ตรวจสอบได้ ไม่ใช้ AI เดา)

1. กรองตามงบ แบรนด์ ความจุ 5G/NFC และ (ถ้าเลือก) เฉพาะรุ่นที่ขายในไทย
2. แปลงสเปกแต่ละด้านเป็นคะแนน 0–100 โดยเทียบกับรุ่นอื่นที่ผ่านการกรอง (percentile rank)
3. ถ่วงน้ำหนักตามการใช้งาน + ด้านที่ผู้ใช้เน้น → คะแนนสเปก
4. ความคุ้มค่า = คะแนนสเปกต่อบาท (เทียบในกลุ่ม) แล้วรวมเป็นคะแนนสุดท้าย
ไม่พึ่ง Streamlit เพื่อให้ทดสอบแยกได้
"""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# มิติ: (คอลัมน์, มากดีกว่า, ชื่อไทย, หน่วยแสดงผล)
DIMENSIONS: dict[str, tuple[str, bool, str, str]] = {
    "performance": ("perf_score", True, "ประสิทธิภาพ", ""),
    "camera": ("camera_mp", True, "กล้องหลัก", "{:.0f} MP"),
    "selfie": ("front_mp", True, "กล้องหน้า", "{:.0f} MP"),
    "battery": ("battery_mah", True, "แบตเตอรี่", "{:,.0f} mAh"),
    "charging": ("charging_w", True, "ชาร์จเร็ว", "{:.0f}W"),
    "display": ("refresh_hz", True, "จอลื่น", "{:.0f}Hz"),
    "storage": ("storage_gb", True, "ความจุ", "{:.0f}GB"),
    "ram": ("ram_gb", True, "RAM", "{:.0f}GB"),
}

USE_CASES: dict[str, dict[str, float]] = {
    "ใช้งานทั่วไป/เรียน": {"performance": 2, "battery": 3, "storage": 2, "ram": 1, "display": 1, "charging": 1, "camera": 1},
    "เล่นเกม": {"performance": 5, "display": 3, "ram": 2, "battery": 3, "charging": 2, "storage": 1},
    "ถ่ายรูป/วิดีโอ": {"camera": 5, "performance": 2, "storage": 3, "battery": 2, "selfie": 1},
    "เซลฟี่/โซเชียล": {"selfie": 5, "camera": 2, "display": 2, "battery": 2, "storage": 1},
    "ทำงาน": {"performance": 3, "ram": 3, "battery": 3, "storage": 2, "charging": 1, "display": 1},
    "แบตอึด/เดินทาง": {"battery": 5, "charging": 3, "performance": 1, "storage": 1},
    "ผู้สูงอายุ/ใช้ง่าย": {"battery": 4, "charging": 1, "camera": 1, "performance": 1},
}
USE_CASE_ICONS = {"ใช้งานทั่วไป/เรียน": "📚", "เล่นเกม": "🎮", "ถ่ายรูป/วิดีโอ": "📸", "เซลฟี่/โซเชียล": "🤳",
                  "ทำงาน": "💼", "แบตอึด/เดินทาง": "🔋", "ผู้สูงอายุ/ใช้ง่าย": "👵"}
PRIORITY_MAP = {"ประสิทธิภาพ": "performance", "กล้อง": "camera", "กล้องหน้า": "selfie", "แบตเตอรี่": "battery",
                "ชาร์จเร็ว": "charging", "จอลื่น": "display", "ความจุ": "storage", "ความคุ้มค่า": "value"}
VALUE_WEIGHT = 2.0
PRIORITY_BONUS = 3.0
GOOD, WEAK = 70, 30  # เกณฑ์ข้อดี/ข้อเสีย


@dataclass
class Request:
    budget_min: float = 0
    budget_max: float | None = 20000
    use_case: str = "ใช้งานทั่วไป/เรียน"
    priorities: list[str] = field(default_factory=list)
    brands: list[str] = field(default_factory=list)
    min_storage: float = 0
    need_5g: bool = False
    need_nfc: bool = False
    thailand_only: bool = True
    note: str = ""

    def describe(self) -> dict:
        return {"งบ_บาท": [self.budget_min, self.budget_max], "ใช้งานหลัก": self.use_case, "เน้น": self.priorities,
                "แบรนด์": self.brands or "ทุกแบรนด์", "ความจุขั้นต่ำ_GB": self.min_storage, "ต้องมี_5G": self.need_5g,
                "ต้องมี_NFC": self.need_nfc, "เฉพาะรุ่นที่ขายในไทย": self.thailand_only, "เพิ่มเติม": self.note}


def weights_for(use_case: str, priorities: list[str] | None = None) -> dict[str, float]:
    w = dict(USE_CASES.get(use_case, USE_CASES["ใช้งานทั่วไป/เรียน"]))
    w["value"] = VALUE_WEIGHT
    for p in priorities or []:
        key = PRIORITY_MAP.get(p, p)
        w[key] = w.get(key, 0) + PRIORITY_BONUS
    return w


def filter_candidates(df: pd.DataFrame, req: Request) -> pd.DataFrame:
    d = df
    if req.thailand_only:
        d = d[d["in_thailand"]]
    if req.brands:
        d = d[d["brand"].isin(req.brands)]
    d = d[d["price_thb"].between(req.budget_min or 0, req.budget_max or np.inf)]
    if req.min_storage:
        d = d[d["storage_max"].fillna(d["storage_gb"]) >= req.min_storage]
    if req.need_5g:
        d = d[d["has_5g"]]
    if req.need_nfc:
        d = d[d["has_nfc"]]
    return d.copy()


def _percentile(series: pd.Series, higher_better: bool = True) -> pd.Series:
    """0–100 ตามอันดับในกลุ่ม: ดีสุด = 100, แย่สุด = 0, ไม่มีข้อมูล = NaN"""
    s = pd.to_numeric(series, errors="coerce")
    n = s.notna().sum()
    if n == 0:
        return s * np.nan
    if n == 1 or s.nunique() == 1:
        return s.where(s.isna(), 100.0)
    r = s.rank(method="average", ascending=higher_better)
    return (r - r.min()) / (r.max() - r.min()) * 100


def score(df: pd.DataFrame, req: Request) -> pd.DataFrame:
    """เพิ่ม s_<มิติ> (0–100), spec_score, s_value, completeness และ score แล้วเรียงจากมากไปน้อย"""
    d = df.copy()
    if d.empty:
        return d.assign(score=pd.Series(dtype=float))
    w = weights_for(req.use_case, req.priorities)
    for dim, (col, higher, _, _) in DIMENSIONS.items():
        d[f"s_{dim}"] = _percentile(d[col], higher)
    dims = [k for k in DIMENSIONS if w.get(k)]
    wv = np.array([w[k] for k in dims], dtype=float)
    S = d[[f"s_{k}" for k in dims]].to_numpy(dtype=float)
    has = ~np.isnan(S)
    present_w = (has * wv).sum(axis=1)
    weighted = np.where(present_w > 0, np.nansum(np.where(has, S, 0) * wv, axis=1) / np.maximum(present_w, 1e-9), np.nan)
    d["completeness"] = present_w / wv.sum() * 100
    d["spec_score"] = weighted * (0.7 + 0.3 * present_w / wv.sum())  # ข้อมูลไม่ครบ = ถูกลดคะแนน
    # ความคุ้มค่า: ถ้ามีราคายุติธรรมจากโมเดล ML ใช้ (ราคาที่ควรเป็น ÷ ราคาจริง) ไม่งั้นใช้คะแนนสเปกต่อบาท
    if "fair_price_thb" in d and d["fair_price_thb"].notna().any():
        d["s_value"] = _percentile(d["fair_price_thb"] / d["price_thb"])
    else:
        d["s_value"] = _percentile(d["spec_score"] / d["price_thb"])
    vw = w.get("value", 0)
    d["score"] = ((d["spec_score"] * wv.sum() + d["s_value"].fillna(d["spec_score"]) * vw) / (wv.sum() + vw)).round(1)
    return d.sort_values(["score", "price_thb"], ascending=[False, True]).reset_index(drop=True)


def recommend(df: pd.DataFrame, req: Request, n: int = 5) -> tuple[pd.DataFrame, int]:
    """คืน (n อันดับแรก, จำนวนรุ่นที่ผ่านการกรอง)"""
    cands = filter_candidates(df, req)
    return score(cands, req).head(n).reset_index(drop=True), len(cands)


# ---------------------------------------------------------------------------
# ข้อดี / ข้อเสีย (อิงคะแนนและตัวเลขจริง)
# ---------------------------------------------------------------------------
def spec_text(row: pd.Series, dim: str) -> str:
    col, _, _, fmt = DIMENSIONS[dim]
    if dim == "performance":
        return str(row.get("chipset") or "")
    v = row.get(col)
    return "" if v is None or pd.isna(v) else fmt.format(v)


def pros_cons(row: pd.Series, req: Request) -> tuple[list[str], list[str]]:
    w = weights_for(req.use_case, req.priorities)
    pros, cons = [], []
    for dim in sorted(DIMENSIONS, key=lambda k: -w.get(k, 0)):
        s, label, spec = row.get(f"s_{dim}"), DIMENSIONS[dim][2], spec_text(row, dim)
        detail = f" ({spec})" if spec else ""
        if s is None or pd.isna(s):
            if w.get(dim, 0) >= 3:
                cons.append(f"ไม่มีข้อมูล{label}")
        elif s >= GOOD and w.get(dim, 0) > 0:
            pros.append(f"{label}เด่นในกลุ่มนี้{detail}")
        elif s <= WEAK and w.get(dim, 0) >= 2:
            cons.append(f"{label}ด้อยกว่ารุ่นอื่นในกลุ่ม{detail}")
    ratio, v = row.get("deal_ratio"), row.get("s_value")
    if ratio is not None and not pd.isna(ratio):  # จากโมเดล ML ราคาที่ควรเป็น
        if ratio <= 0.85:
            pros.append(f"ราคาต่ำกว่าที่ควรเป็นตามสเปก ~{(1 - ratio) * 100:.0f}% (โมเดล ML)")
        elif ratio >= 1.15:
            cons.append(f"ราคาสูงกว่าที่ควรเป็นตามสเปก ~{(ratio - 1) * 100:.0f}% (โมเดล ML)")
    elif v is not None and not pd.isna(v):
        if v >= GOOD:
            pros.append("คุ้มค่าต่อราคาเมื่อเทียบกับรุ่นอื่น")
        elif v <= WEAK:
            cons.append("ราคาสูงเมื่อเทียบกับสเปก")
    if row.get("has_nfc"):
        pros.append("มี NFC (จ่ายเงิน/แตะบัตรได้)")
    if not row.get("has_5g", True):
        cons.append("ไม่รองรับ 5G")
    return pros[:4], cons[:4]


def youtube_search_url(name: str) -> str:
    return "https://www.youtube.com/results?search_query=" + urllib.parse.quote_plus(f"รีวิว {name}")
