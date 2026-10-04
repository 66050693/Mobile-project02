"""คำอธิบายเชิงลึกจากผลจัดอันดับ (ไม่ใช้ AI คำนวณจากตัวเลขจริง)

- why_not: ทำไมรุ่นที่ผู้ใช้สนใจไม่ติด 5 อันดับ
- budget_upgrade: ถ้าเพิ่มงบอีกนิดจะได้รุ่นที่ดีขึ้นแค่ไหน
- value_frontier: รุ่นที่ "คุ้มที่สุด" ในแต่ละระดับราคา (ไม่มีรุ่นไหนถูกกว่าและคะแนนสูงกว่า)
ไม่พึ่ง Streamlit เพื่อให้ทดสอบแยกได้
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from scoring_service import DIMENSIONS, Request, filter_candidates, score, spec_text, weights_for

GAP = 15  # ต่างกันกี่คะแนนรายด้านจึงนับว่า "ด้อยกว่าชัดเจน"


def filter_reasons(row: pd.Series, req: Request) -> list[str]:
    """เหตุผลที่รุ่นนี้ไม่ผ่านตัวกรอง (ว่าง = ผ่าน)"""
    out = []
    price = row.get("price_thb")
    if req.thailand_only and not row.get("in_thailand"):
        out.append("ไม่อยู่ในรายชื่อรุ่นที่ขายอย่างเป็นทางการในไทย (ปิดตัวกรองนี้ได้)")
    if req.brands and row.get("brand") not in req.brands:
        out.append(f"แบรนด์ {row.get('brand')} ไม่อยู่ในแบรนด์ที่เลือก")
    if pd.notna(price) and req.budget_max and price > req.budget_max:
        out.append(f"ราคา ฿{price:,.0f} เกินงบ ฿{req.budget_max:,.0f} อยู่ ฿{price - req.budget_max:,.0f}")
    if pd.notna(price) and price < (req.budget_min or 0):
        out.append(f"ราคา ฿{price:,.0f} ต่ำกว่างบขั้นต่ำที่ตั้งไว้")
    storage = row.get("storage_max") if pd.notna(row.get("storage_max")) else row.get("storage_gb")
    if req.min_storage and (pd.isna(storage) or storage < req.min_storage):
        out.append(f"ความจุสูงสุด {storage:.0f}GB ไม่ถึง {req.min_storage}GB" if pd.notna(storage) else "ไม่มีข้อมูลความจุ")
    if req.need_5g and not row.get("has_5g"):
        out.append("ไม่รองรับ 5G")
    if req.need_nfc and not row.get("has_nfc"):
        out.append("ไม่มี NFC")
    return out


def why_not(phones: pd.DataFrame, req: Request, name: str, n: int = 5) -> dict:
    """อธิบายว่ารุ่น `name` อยู่อันดับไหน และแพ้รุ่นสุดท้ายที่ติด n อันดับตรงไหน"""
    match = phones[phones["name"] == name]
    if match.empty:
        return {"status": "not_found", "reasons": [f"ไม่พบรุ่น {name} ในฐานข้อมูล"]}
    row = match.iloc[0]
    blocked = filter_reasons(row, req)
    if blocked:
        return {"status": "filtered", "name": name, "reasons": blocked}
    ranked = score(filter_candidates(phones, req), req)
    pos = int(ranked.index[ranked["name"] == name][0])
    me = ranked.iloc[pos]
    if pos < n:
        return {"status": "in_top", "name": name, "rank": pos + 1, "reasons": [f"รุ่นนี้ติดอันดับ {pos + 1} อยู่แล้ว"]}
    rival = ranked.iloc[n - 1]
    w = weights_for(req.use_case, req.priorities)
    reasons = []
    for dim in sorted(DIMENSIONS, key=lambda k: -w.get(k, 0)):
        if not w.get(dim):
            continue
        a, b = me.get(f"s_{dim}"), rival.get(f"s_{dim}")
        label = DIMENSIONS[dim][2]
        if pd.isna(a) and pd.notna(b):
            reasons.append(f"ไม่มีข้อมูล{label} จึงถูกหักคะแนน")
        elif pd.notna(a) and pd.notna(b) and b - a >= GAP:
            mine, theirs = spec_text(me, dim), spec_text(rival, dim)
            detail = f" ({mine} เทียบกับ {theirs})" if mine and theirs else ""
            reasons.append(f"{label}ด้อยกว่า{detail}")
    dp = me["price_thb"] - rival["price_thb"]
    if dp > 0:
        reasons.append(f"แพงกว่า ฿{dp:,.0f}")
    if pd.notna(me.get("s_value")) and pd.notna(rival.get("s_value")) and rival["s_value"] - me["s_value"] >= GAP:
        reasons.append("ความคุ้มค่าต่อราคาน้อยกว่า")
    return {"status": "ranked", "name": name, "rank": pos + 1, "of": len(ranked), "score": float(me["score"]),
            "rival": rival["name"], "rival_rank": n, "rival_score": float(rival["score"]),
            "reasons": reasons[:5] or ["คะแนนรวมใกล้กัน แต่รุ่นอื่นสมดุลกว่าเล็กน้อยสำหรับการใช้งานนี้"]}


def budget_upgrade(phones: pd.DataFrame, req: Request, steps: tuple[int, ...] = (2000, 5000), min_gain: float = 5) -> list[dict]:
    """ถ้าเพิ่มงบ จะได้รุ่นที่คะแนนสูงกว่าอันดับ 1 ปัจจุบันเท่าไร (ให้คะแนนบนกลุ่มงบที่ใหญ่สุดเพื่อเทียบกันได้)"""
    if not req.budget_max:
        return []
    wide = replace(req, budget_max=req.budget_max + max(steps))
    ranked = score(filter_candidates(phones, wide), wide)
    if ranked.empty:
        return []
    now = ranked[ranked["price_thb"] <= req.budget_max]
    best_now = now.iloc[0] if len(now) else None
    base_score = float(best_now["score"]) if best_now is not None else 0.0
    out, seen = [], set()
    for step in sorted(steps):
        pool = ranked[(ranked["price_thb"] > req.budget_max) & (ranked["price_thb"] <= req.budget_max + step)]
        if pool.empty:
            continue
        top = pool.iloc[0]
        gain = float(top["score"]) - base_score
        if gain >= min_gain and top["name"] not in seen:
            seen.add(top["name"])
            out.append({"extra": step, "name": top["name"], "price": float(top["price_thb"]), "gain": round(gain, 1),
                        "vs": None if best_now is None else best_now["name"],
                        "better_at": [DIMENSIONS[d][2] for d in DIMENSIONS
                                      if best_now is not None and pd.notna(top.get(f"s_{d}")) and pd.notna(best_now.get(f"s_{d}"))
                                      and top[f"s_{d}"] - best_now[f"s_{d}"] >= GAP][:3]})
    return out


def value_frontier(ranked: pd.DataFrame) -> pd.Series:
    """True = ไม่มีรุ่นอื่นที่ราคาถูกกว่าหรือเท่ากันแต่คะแนนสูงกว่า (เส้นความคุ้มค่า)"""
    if ranked.empty:
        return pd.Series(dtype=bool)
    d = ranked[["price_thb", "spec_score"]].copy()
    order = d.sort_values(["price_thb", "spec_score"], ascending=[True, False]).index
    best, flags = -np.inf, {}
    for i in order:
        s = d.at[i, "spec_score"]
        flags[i] = bool(pd.notna(s) and s > best)
        if pd.notna(s):
            best = max(best, s)
    return pd.Series(flags).reindex(ranked.index).fillna(False)
