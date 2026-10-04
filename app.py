"""Mobile AI Recommender: หามือถือ 5 รุ่นที่เหมาะกับงบและการใช้งาน (เน้นรุ่นที่ขายในไทย)"""
from __future__ import annotations

import json

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import ui
from ai_service import compact, explain, has_ai_key
from config import DEFAULT_INR_TO_THB, TOP_N
from assistant_service import ChatTools, chat, parse_request
from dataset_service import apply_images, apply_manual_specs, apply_prices, coverage, load_dataset, load_prices
from firebase_auth import guest_allowed, login_user, register_user, reset_password
from insight_service import budget_upgrade, value_frontier, why_not
from ml_service import PriceModel, Segments, apply_ml, segment_phones, train_price_model
from scoring_service import (
    DIMENSIONS, USE_CASE_ICONS, USE_CASES, Request, filter_candidates, pros_cons, score, spec_text,
)
from youtube_service import review_videos, search_link

st.set_page_config(page_title="Mobile AI Recommender", page_icon="📱", layout="wide")
ui.apply_theme()

PRIORITIES = ["ประสิทธิภาพ", "กล้อง", "กล้องหน้า", "แบตเตอรี่", "ชาร์จเร็ว", "จอลื่น", "ความจุ", "ความคุ้มค่า"]
RADAR_COLORS = [ui.INDIGO, "#E07A00", "#0E7A4F"]


# ---------------------------------------------------------------------------
# state และ cache
# ---------------------------------------------------------------------------
def init_state() -> None:
    defaults = {"user": None, "result": None, "prices": None, "thailand_only": True, "chat": [], "parse_note": "",
                # ค่าเริ่มต้นของตัวกรอง (ตั้งใน session ครั้งเดียว ไม่ส่ง default ให้ widget ซ้ำ จะได้ไม่มีคำเตือน)
                "budget": (0, 15000), "use_case": "ใช้งานทั่วไป/เรียน", "priorities": []}
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


@st.cache_data(show_spinner="กำลังโหลดข้อมูลมือถือ...")
def base_dataset() -> pd.DataFrame:
    return apply_images(apply_manual_specs(load_dataset()))


@st.cache_resource(show_spinner="กำลังเทรนโมเดล Machine Learning (ครั้งแรกครั้งเดียว)...")
def ml_models() -> tuple[PriceModel, Segments]:
    """เทรนครั้งเดียวต่อเซิร์ฟเวอร์ แล้วใช้ซ้ำทุกผู้ใช้ (ข้อมูลเปลี่ยนเมื่อ deploy ใหม่เท่านั้น)"""
    d = apply_prices(base_dataset(), load_prices(), DEFAULT_INR_TO_THB)
    return train_price_model(d), segment_phones(d)


@st.cache_data(show_spinner=False, ttl=86400)
def cached_explain(request_json: str, picks_json: str) -> dict:
    return explain(json.loads(request_json), json.loads(picks_json))


@st.cache_data(show_spinner=False, ttl=86400 * 7)
def cached_videos(name: str) -> list[dict]:
    return review_videos(name)


def current_prices() -> pd.DataFrame:
    if st.session_state.prices is None:
        st.session_state.prices = load_prices()
    return st.session_state.prices


def show_all_models() -> None:
    st.session_state.thailand_only = False
    st.session_state.result = None
    st.session_state.run_again = True


def fmt(value, unit: str = "", decimals: int = 0) -> str:
    """ตัวเลขอ่านง่าย: 8.0 → 8, 32150.0 → 32,150 ค่าว่าง → ไม่มีข้อมูล"""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return "ไม่มีข้อมูล"
    if isinstance(value, (bool,)) or str(value) in ("True", "False"):
        return "มี" if str(value) == "True" else "ไม่มี"
    if isinstance(value, (int, float)):
        text = f"{value:,.{decimals}f}"
        return f"{text} {unit}".strip()
    return str(value)


COMPARE_ROWS = [  # (หัวข้อ, คอลัมน์, หน่วย, ทศนิยม, มากดีกว่า)
    ("ราคา", "price_thb", "บาท", 0, False), ("ชิป", "chipset", "", 0, None), ("RAM", "ram_gb", "GB", 0, True),
    ("ความจุเริ่มต้น", "storage_gb", "GB", 0, True), ("กล้องหลัก", "camera_mp", "MP", 0, True),
    ("กล้องหน้า", "front_mp", "MP", 0, True), ("แบตเตอรี่", "battery_mah", "mAh", 0, True),
    ("ชาร์จเร็ว", "charging_w", "W", 0, True), ("หน้าจอ", "display_in", "นิ้ว", 1, None),
    ("รีเฟรชเรต", "refresh_hz", "Hz", 0, True), ("5G", "has_5g", "", 0, None), ("NFC", "has_nfc", "", 0, None),
    ("ระบบ", "os", "", 0, None),
]


def compare_html(sel: pd.DataFrame) -> str:
    rows = []
    for label, col, unit, dec, higher in COMPARE_ROWS:
        raw = list(sel[col])
        values = [fmt(v, unit, dec) for v in raw]
        best = None
        nums = pd.to_numeric(pd.Series(raw), errors="coerce")
        if higher is not None and nums.notna().sum() >= 2 and nums.nunique() > 1:
            best = int(nums.idxmax() if higher else nums.idxmin())
        rows.append((label, values, best))
    rows.append(("ที่มาราคา", ["ราคาไทย" if k == "ราคาไทย" else "ราคาประมาณ" for k in sel["price_kind"]], None))
    return ui.compare_table(list(sel["name"]), rows)


BUDGET_MAX = 80000


def apply_text_request() -> None:
    """callback ของปุ่ม “ให้ AI ตั้งค่าให้”: แปลงข้อความแล้วตั้งค่าตัวกรองทั้งหมด จากนั้นค้นหาทันที"""
    text = st.session_state.get("nl_text", "").strip()
    if not text:
        st.session_state.parse_note = "พิมพ์สิ่งที่อยากได้ก่อน เช่น งบไม่เกินหมื่น เล่นเกมลื่น แบตอึด"
        return
    p = parse_request(text, st.session_state.get("brand_options", []))
    if p.budget_max:
        st.session_state.budget = (min(p.budget_min, BUDGET_MAX), min(p.budget_max, BUDGET_MAX))
    if p.use_case:
        st.session_state.use_case = p.use_case
    st.session_state.priorities = p.priorities or []
    st.session_state.brands = p.brands or []
    st.session_state.min_storage = p.min_storage if p.min_storage in (0, 128, 256, 512) else 0
    st.session_state.need_5g, st.session_state.need_nfc = p.need_5g, p.need_nfc
    parts = []
    if p.budget_max:
        parts.append(f"งบ ฿{p.budget_min:,}–฿{p.budget_max:,}" if p.budget_min else f"งบไม่เกิน ฿{p.budget_max:,}")
    if p.use_case:
        parts.append(p.use_case)
    if p.priorities:
        parts.append("เน้น" + ", ".join(p.priorities))
    if p.brands:
        parts.append("แบรนด์ " + ", ".join(p.brands))
    if p.min_storage:
        parts.append(f"{p.min_storage}GB ขึ้นไป")
    if p.need_5g:
        parts.append("5G")
    if p.need_nfc:
        parts.append("NFC")
    who = "AI" if p.source == "ai" else "ระบบ"
    st.session_state.parse_note = (f"{who}เข้าใจว่า: " + ", ".join(parts)) if parts else \
        "ยังจับงบหรือการใช้งานจากข้อความไม่ได้ ลองระบุตัวเลขงบ เช่น “ไม่เกิน 12000”"
    st.session_state.run_again = bool(parts)


def value_chart(ranked: pd.DataFrame, picks: pd.DataFrame) -> go.Figure:
    """ราคา (แกนนอน) เทียบความเหมาะสม (แกนตั้ง): มุมซ้ายบน = คุ้มที่สุด"""
    top = set(picks["name"])
    frontier = ranked[value_frontier(ranked)].sort_values("price_thb")
    rest = ranked[~ranked["name"].isin(top)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=rest["price_thb"], y=rest["score"], mode="markers", name="รุ่นอื่นในงบ",
                             marker=dict(size=8, color="#B7BECC"), text=rest["name"],
                             hovertemplate="%{text}<br>฿%{x:,.0f} | %{y:.0f} คะแนน<extra></extra>"))
    fig.add_trace(go.Scatter(x=frontier["price_thb"], y=frontier["score"], mode="lines", name="เส้นความคุ้มค่า",
                             line=dict(color=ui.INDIGO, width=1.5, dash="dot"), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=picks["price_thb"], y=picks["score"], mode="markers+text", name="5 อันดับที่แนะนำ",
                             marker=dict(size=14, color=ui.INDIGO, line=dict(color="#fff", width=2)),
                             text=[str(i) for i in range(1, len(picks) + 1)], textposition="middle center",
                             textfont=dict(color="#fff", size=11), customdata=picks["name"],
                             hovertemplate="%{customdata}<br>฿%{x:,.0f} | %{y:.0f} คะแนน<extra></extra>"))
    fig.update_layout(height=380, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Anuphan, sans-serif", size=13, color=ui.INK),
                      legend=dict(orientation="h", y=-0.2), hovermode="closest")
    fig.update_xaxes(title_text="ราคา (บาท)", gridcolor=ui.LINE, tickformat=",")
    fig.update_yaxes(title_text="ความเหมาะสม (คะแนน)", gridcolor=ui.LINE, range=[0, 105])
    return fig


def ml_chips(r) -> str:
    """ป้ายกลุ่ม (K-Means) และราคาเทียบสเปก (Random Forest) บนการ์ด"""
    chips = []
    if r.get("segment"):
        chips.append(f'<span class="chip">กลุ่ม: {ui.esc(r["segment"])}</span>')
    label, ratio = r.get("deal_label"), r.get("deal_ratio")
    if label:
        kind = "good" if ratio <= 0.85 else "bad" if ratio >= 1.15 else ""
        chips.append(f'<span class="chip {kind}">{ui.esc(label)} (ควรอยู่ที่ราว {ui.baht(r["fair_price_thb"])})</span>')
    return f'<div class="chips" style="margin-left:2.6rem">{"".join(chips)}</div>' if chips else ""


def _base_layout(fig: go.Figure, height: int = 380) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(family="Anuphan, sans-serif", size=13, color=ui.INK),
                      legend=dict(orientation="h", y=-0.22), hovermode="closest")
    fig.update_xaxes(gridcolor=ui.LINE)
    fig.update_yaxes(gridcolor=ui.LINE)
    return fig


def actual_vs_pred_chart(tp: pd.DataFrame, rate: float) -> go.Figure:
    a, p = tp["actual"] * rate, tp["predicted"] * rate
    lo, hi = float(min(a.min(), p.min())) * 0.9, float(max(a.max(), p.max())) * 1.1
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[lo, hi], y=[lo, hi], mode="lines", name="ทายถูกพอดี",
                             line=dict(color=ui.MUTED, dash="dot", width=1), hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=a, y=p, mode="markers", name="รุ่นในชุดทดสอบ", text=tp["name"],
                             marker=dict(size=8, color=ui.INDIGO, opacity=0.7),
                             hovertemplate="%{text}<br>จริง ฿%{x:,.0f}<br>ทาย ฿%{y:,.0f}<extra></extra>"))
    _base_layout(fig)
    fig.update_xaxes(title_text="ราคาจริง (บาท, สเกล log)", type="log", tickformat=",")
    fig.update_yaxes(title_text="ราคาที่โมเดลทาย (บาท, สเกล log)", type="log", tickformat=",")
    return fig


def importance_chart(imp: pd.DataFrame) -> go.Figure:
    d = imp[imp["percent"] >= 0.5].sort_values("percent")
    fig = go.Figure(go.Bar(x=d["percent"], y=d["group"], orientation="h", marker_color=ui.INDIGO,
                           hovertemplate="%{y}: %{x:.1f}%<extra></extra>"))
    _base_layout(fig, height=max(260, 34 * len(d) + 60))
    fig.update_xaxes(title_text="ความสำคัญต่อการทายราคา (%)")
    return fig


SEGMENT_COLORS = [ui.INDIGO, "#E07A00", "#0E7A4F", "#B4372F", "#7C3AED", "#0284C7", "#A16207"]


def segment_chart(coords: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    for i, (seg, part) in enumerate(coords.groupby("segment", sort=False)):
        fig.add_trace(go.Scatter(x=part["x"], y=part["y"], mode="markers", name=seg, text=part["name"],
                                 marker=dict(size=7, color=SEGMENT_COLORS[i % len(SEGMENT_COLORS)], opacity=0.75),
                                 hovertemplate="%{text}<extra>" + seg + "</extra>"))
    _base_layout(fig, height=420)
    fig.update_xaxes(title_text="องค์ประกอบหลักที่ 1 (PCA)", showticklabels=False, zeroline=False)
    fig.update_yaxes(title_text="องค์ประกอบหลักที่ 2 (PCA)", showticklabels=False, zeroline=False)
    return fig


def radar(rows: pd.DataFrame, names: list[str]) -> go.Figure:
    dims = list(DIMENSIONS)
    labels = [DIMENSIONS[d][2] for d in dims]
    fig = go.Figure()
    for i, (_, r) in enumerate(rows.iterrows()):
        values = [0 if pd.isna(r.get(f"s_{d}")) else r[f"s_{d}"] for d in dims]
        fig.add_trace(go.Scatterpolar(r=values + values[:1], theta=labels + labels[:1], name=names[i], fill="toself",
                                      opacity=0.55, line=dict(color=RADAR_COLORS[i % 3], width=2)))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], showticklabels=False, gridcolor=ui.LINE),
                                 angularaxis=dict(gridcolor=ui.LINE)),
                      height=420, margin=dict(l=40, r=40, t=20, b=20), paper_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Anuphan, sans-serif", size=14, color=ui.INK),
                      legend=dict(orientation="h", y=-0.08))
    return fig


init_state()

# ---------------------------------------------------------------------------
# ล็อกอิน
# ---------------------------------------------------------------------------
if st.session_state.user is None:
    left, right = st.columns([5, 4], gap="large")
    with left:
        ui.hero("เลือกมือถือที่ใช่ ในงบที่มี",
                "บอกงบกับสิ่งที่ใช้บ่อย แล้วดู 5 รุ่นที่เหมาะที่สุด พร้อมข้อดีข้อเสียจากสเปกจริงและคลิปรีวิว")
        ui.html_block(ui.chips(["📚 เรียน", "🎮 เล่นเกม", "📸 ถ่ายรูป", "🔋 แบตอึด", "💼 ทำงาน"]))
    with right:
        with st.container(border=True):
            tab_login, tab_register, tab_reset = st.tabs(["เข้าสู่ระบบ", "สมัครสมาชิก", "ลืมรหัสผ่าน"])
            with tab_login:
                with st.form("login_form"):
                    email = st.text_input("อีเมล")
                    password = st.text_input("รหัสผ่าน", type="password")
                    submitted = st.form_submit_button("เข้าสู่ระบบ", type="primary", use_container_width=True)
                if submitted:
                    if not email or not password:
                        st.error("กรอกอีเมลและรหัสผ่านก่อน")
                    else:
                        with st.spinner("กำลังเข้าสู่ระบบ..."):
                            result = login_user(email, password)
                        if result["ok"]:
                            st.session_state.user = result
                            st.rerun()
                        st.error(result["message"])
            with tab_register:
                with st.form("register_form"):
                    reg_email = st.text_input("อีเมล", key="reg_email")
                    reg_pw = st.text_input("รหัสผ่าน (อย่างน้อย 6 ตัว)", type="password")
                    reg_pw2 = st.text_input("ยืนยันรหัสผ่าน", type="password")
                    submitted = st.form_submit_button("สร้างบัญชี", use_container_width=True)
                if submitted:
                    if not reg_email or not reg_pw:
                        st.error("กรอกข้อมูลให้ครบ")
                    elif reg_pw != reg_pw2:
                        st.error("รหัสผ่านสองช่องไม่ตรงกัน")
                    else:
                        with st.spinner("กำลังสร้างบัญชี..."):
                            result = register_user(reg_email, reg_pw)
                        (st.success if result["ok"] else st.error)(
                            "สร้างบัญชีแล้ว เข้าสู่ระบบได้เลย" if result["ok"] else result["message"])
            with tab_reset:
                with st.form("reset_form"):
                    reset_email = st.text_input("อีเมลที่สมัครไว้")
                    sent = st.form_submit_button("ส่งลิงก์ตั้งรหัสใหม่", use_container_width=True)
                if sent:
                    r = reset_password(reset_email) if reset_email else {"ok": False, "message": "กรอกอีเมลก่อน"}
                    (st.success if r["ok"] else st.error)(r["message"])
            if guest_allowed():
                if st.button("ลองใช้โดยไม่ล็อกอิน (โหมดทดสอบ)", key="guest", use_container_width=True):
                    st.session_state.user = {"ok": True, "email": "ผู้ทดสอบ"}
                    st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# ข้อมูล + แถบข้าง
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"**{ui.esc(st.session_state.user.get('email', '-'))}**")
    if st.button("ออกจากระบบ", key="logout"):
        st.session_state.user = None
        st.session_state.result = None
        st.rerun()

try:
    phones = apply_prices(base_dataset(), current_prices(), DEFAULT_INR_TO_THB)
    price_model, segments = ml_models()
    phones = apply_ml(phones, price_model, segments, DEFAULT_INR_TO_THB)
except (FileNotFoundError, ValueError) as err:
    st.error(f"อ่านไฟล์ข้อมูลมือถือไม่ได้: {err} ตรวจว่ามีไฟล์ data/smartphones_2026.csv")
    st.stop()
cov = coverage(phones)

tab_find, tab_compare, tab_browse, tab_ml, tab_about = st.tabs(
    ["หามือถือ", "เทียบเอง", "ดูทุกรุ่น", "โมเดล ML", "วิธีคิดคะแนน"])

# ---------------------------------------------------------------------------
# แท็บ: หามือถือ
# ---------------------------------------------------------------------------
with tab_find:
    ui.hero("เลือกมือถือที่ใช่ ในงบที่มี", "พิมพ์บอกสิ่งที่อยากได้ หรือตั้งค่าเองด้านล่าง ระบบจะเทียบสเปกจริงแล้วเลือก 5 รุ่นที่คุ้มที่สุดให้")
    st.session_state.brand_options = sorted(phones["brand"].unique())
    with st.container(border=True):
        t1, t2 = st.columns([4, 1.3], vertical_alignment="bottom")
        with t1:
            st.text_input("บอกเป็นประโยคก็ได้", key="nl_text",
                          placeholder="เช่น งบไม่เกินหมื่น เล่น ROV ลื่น แบตอึด หรือ ซื้อให้แม่ 8000–12000 มี NFC")
        with t2:
            st.button("ตั้งค่าให้อัตโนมัติ", key="nl_go", on_click=apply_text_request, use_container_width=True)
        if st.session_state.parse_note:
            st.markdown(f'<p class="note">{ui.esc(st.session_state.parse_note)}</p>', unsafe_allow_html=True)
    with st.container(border=True):
        budget = st.slider("งบประมาณ (บาท)", 0, BUDGET_MAX, step=500, key="budget", format="฿%d")
        use_case = ui.pills("ใช้ทำอะไรเป็นหลัก", list(USE_CASES), multi=False, default="ใช้งานทั่วไป/เรียน", key="use_case",
                            format_func=lambda x: f"{USE_CASE_ICONS.get(x, '')} {x}")
        priorities = ui.pills("อยากให้เด่นเรื่องไหนเป็นพิเศษ (เลือกได้หลายข้อ)", PRIORITIES, multi=True, default=[],
                              key="priorities")
        st.markdown("**ตัวกรองเพิ่มเติม**")
        c1, c2 = st.columns(2)
        with c1:
            brands = st.multiselect("แบรนด์", sorted(phones["brand"].unique()), key="brands",
                                    placeholder="ทุกแบรนด์")
            min_storage = st.selectbox("ความจุขั้นต่ำ", [0, 128, 256, 512], key="min_storage",
                                       format_func=lambda x: "ไม่กำหนด" if x == 0 else f"{x} GB ขึ้นไป")
        with c2:
            need_5g = st.checkbox("ต้องรองรับ 5G", key="need_5g")
            need_nfc = st.checkbox("ต้องมี NFC", key="need_nfc")
            st.toggle("เฉพาะรุ่นที่ขายอย่างเป็นทางการในไทย", key="thailand_only",
                      help=f"รุ่นที่แบรนด์วางขายในไทยอย่างเป็นทางการ ({cov['thai_matched']} รุ่น) ปิดเพื่อดูทุกรุ่น")
        note = st.text_area("บอกเพิ่มได้ (AI จะนำไปอธิบาย)", key="note", max_chars=300,
                            placeholder="เช่น ถ่ายกลางคืนบ่อย มือเล็ก ใช้ LINE ทั้งวัน")
        go_clicked = st.button(f"หา {TOP_N} รุ่นที่เหมาะที่สุด", type="primary", key="go", use_container_width=True)

    if go_clicked or st.session_state.pop("run_again", False):
        req = Request(budget_min=budget[0], budget_max=budget[1] or None, use_case=use_case, priorities=priorities,
                      brands=brands, min_storage=min_storage, need_5g=need_5g, need_nfc=need_nfc,
                      thailand_only=st.session_state.thailand_only, note=note)
        ranked = score(filter_candidates(phones, req), req)
        picks, n_cands = ranked.head(TOP_N).reset_index(drop=True), len(ranked)
        rows = [compact(r, *pros_cons(r, req)) for _, r in picks.iterrows()]
        ai = None
        if rows:
            with st.spinner("กำลังสรุปคำแนะนำ..."):
                ai = cached_explain(json.dumps(req.describe(), ensure_ascii=False, sort_keys=True),
                                    json.dumps(rows, ensure_ascii=False))
        st.session_state.result = {"req": req, "picks": picks, "rows": rows, "ai": ai, "n": n_cands, "ranked": ranked}
        st.session_state.chat = []

    res = st.session_state.result
    if res is None:
        st.markdown(f'<p class="note">ฐานข้อมูลมี {cov["dataset_models"]} รุ่น ในจำนวนนี้ {cov["thai_matched"]} รุ่น'
                    f'อยู่ในรายชื่อขายในไทย</p>', unsafe_allow_html=True)
    elif res["picks"].empty:
        st.warning("ไม่มีรุ่นที่ตรงทุกเงื่อนไข ลองขยายงบ ลดความจุขั้นต่ำ หรือเอาตัวกรองแบรนด์/5G/NFC ออก")
        if res["req"].thailand_only:
            st.button("ค้นจากทุกรุ่นในฐานข้อมูล", on_click=show_all_models, key="widen_empty")
    else:
        req, ai, picks = res["req"], res["ai"], res["picks"]
        scope = "รุ่นที่ขายในไทย" if req.thailand_only else "ทุกรุ่นในฐานข้อมูล"
        st.markdown(f'<p class="note">เทียบ {res["n"]} รุ่นจาก{scope} ในงบ {ui.baht(req.budget_min)}–{ui.baht(req.budget_max)}'
                    f' สำหรับ{req.use_case}</p>', unsafe_allow_html=True)
        if res["n"] < TOP_N and req.thailand_only:
            st.info(f"มีรุ่นที่ขายในไทยตรงเงื่อนไขแค่ {res['n']} รุ่น")
            st.button("ดูตัวเลือกจากทุกรุ่นในฐานข้อมูล", on_click=show_all_models, key="widen")
        if ai.get("error"):
            st.caption(ai["error"])
        if ai.get("summary"):
            ui.html_block(f'<div class="summary">{ui.esc(ai["summary"])}</div>')

        for i, (row, item) in enumerate(zip(res["rows"], ai["items"]), start=1):
            r = picks.iloc[i - 1]
            with st.container(border=True):
                pic, head, price = st.columns([0.9, 3, 1.3])
                with pic:
                    ui.html_block(ui.phone_image(r.get("image", ""), r["name"], r["brand"]))
                sub = ", ".join(x for x in (spec_text(r, "performance"), spec_text(r, "storage"),
                                            spec_text(r, "battery")) if x)
                if not r["in_thailand"]:
                    sub += " (ไม่อยู่ในรายชื่อขายในไทย)"
                with head:
                    ui.html_block(ui.pick_header(i, r["name"], sub) + ml_chips(r))
                with price:
                    ui.html_block(ui.price_block(r["price_thb"], r["price_kind"], highlight=i == 1))
                ui.html_block(ui.meter(r["score"]) + f'<p class="why">{ui.esc(item.get("why", ""))}</p>')
                good, bad = st.columns(2)
                with good:
                    ui.html_block('<div class="list-title">ข้อดี</div>' + ui.chips(item.get("pros", []), "good"))
                with bad:
                    ui.html_block('<div class="list-title">ข้อควรรู้</div>' + ui.chips(item.get("cons", []), "bad"))
                if item.get("best_for"):
                    ui.html_block(f'<p class="note">เหมาะกับ: {ui.esc(item["best_for"])}</p>')
                videos = cached_videos(r["name"])
                if videos:
                    links = "".join(f'<li><a href="{ui.esc(v["url"])}" target="_blank" rel="noopener">{ui.esc(v["title"])}</a>'
                                    f' <span class="note">{ui.esc(v["channel"])}</span></li>' for v in videos)
                    ui.html_block(f'<div class="list-title">คลิปรีวิว</div><ul>{links}</ul>')
                else:
                    st.link_button(f"ดูรีวิว {r['name']} บน YouTube", search_link(r["name"]))

        st.subheader("เทียบจุดเด่นแต่ละด้าน")
        top3 = picks.head(3)
        st.plotly_chart(radar(top3, list(top3["name"])), use_container_width=True, config={"displayModeBar": False})
        st.caption("คะแนนแต่ละด้าน 0–100 เทียบกับรุ่นอื่นที่ผ่านการกรองในรอบนี้ (100 = ดีที่สุดในกลุ่ม)")
        st.subheader("สเปกเทียบกัน")
        ui.html_block(compare_html(picks))
        if len(res["ranked"]) > TOP_N:
            st.subheader("ราคาเทียบความเหมาะสม")
            st.plotly_chart(value_chart(res["ranked"], picks), use_container_width=True, config={"displayModeBar": False})
            st.caption("แต่ละจุดคือ 1 รุ่นที่ตรงเงื่อนไข จุดที่อยู่สูงและชิดซ้ายคือได้สเปกดีในราคาต่ำ "
                       "เส้นประเชื่อมรุ่นที่ไม่มีรุ่นไหนถูกกว่าและดีกว่า")

        ups = budget_upgrade(phones, req)
        if ups:
            st.subheader("ถ้าเพิ่มงบอีกนิด")
            for u in ups:
                better = f" เด่นกว่าเรื่อง{', '.join(u['better_at'])}" if u["better_at"] else ""
                ui.html_block(f'<div class="upgrade">เพิ่มงบอีก <b>฿{u["extra"]:,}</b> ได้ <b>{ui.esc(u["name"])}</b> '
                              f'(฿{u["price"]:,.0f}) คะแนนสูงกว่า{ui.esc(u["vs"] or "อันดับ 1")} {u["gain"]:.0f} คะแนน'
                              f'{ui.esc(better)}</div>')

        st.subheader("ทำไมไม่ใช่รุ่นนี้?")
        pool_names = sorted(phones[phones["in_thailand"]]["name"] if req.thailand_only else phones["name"])
        w1, w2 = st.columns([4, 1.3], vertical_alignment="bottom")
        with w1:
            target = st.selectbox("เลือกรุ่นที่สนใจแต่ไม่อยู่ในอันดับ", pool_names, index=None, key="why_pick",
                                  placeholder="พิมพ์ชื่อรุ่น")
        with w2:
            ask_why = st.button("ดูเหตุผล", key="why_go", use_container_width=True, disabled=target is None)
        if ask_why and target:
            wn = why_not(phones, req, target)
            if wn["status"] == "ranked":
                head_txt = (f"{target} อยู่อันดับ {wn['rank']} จาก {wn['of']} รุ่น ({wn['score']:.0f} คะแนน) "
                            f"เทียบกับอันดับ {wn['rival_rank']} {wn['rival']} ({wn['rival_score']:.0f} คะแนน)")
            elif wn["status"] == "filtered":
                head_txt = f"{target} ไม่ผ่านเงื่อนไขที่ตั้งไว้"
            else:
                head_txt = target
            items = "".join(f"<li>{ui.esc(x)}</li>" for x in wn["reasons"])
            ui.html_block(f'<div class="upgrade"><b>{ui.esc(head_txt)}</b><ul class="reason-list">{items}</ul></div>')

        st.subheader("ถาม AI ต่อ")
        if not has_ai_key():
            st.info("ตั้งค่า GROQ_API_KEY ใน Secrets เพื่อเปิดแชทถามต่อ เช่น “อันดับ 1 กับ 2 ต่างกันยังไง”")
        else:
            for m in st.session_state.chat:
                with st.chat_message(m["role"]):
                    st.markdown(m["content"])
            with st.form("chat_form", clear_on_submit=True):
                q1, q2 = st.columns([5, 1], vertical_alignment="bottom")
                with q1:
                    question = st.text_input("คำถาม", placeholder="เช่น อันดับ 1 กับ 2 ต่างกันยังไง, ถ้าเพิ่มงบ 3,000 ได้อะไร")
                with q2:
                    sent = st.form_submit_button("ถาม", use_container_width=True)
            if sent and question.strip():
                with st.spinner("AI กำลังตอบ..."):
                    try:
                        out = chat(question, st.session_state.chat, ChatTools(phones, req))
                        answer = out["answer"]
                    except Exception as err:
                        answer = f"ถาม AI ไม่สำเร็จ: {str(err)[:200]}"
                st.session_state.chat += [{"role": "user", "content": question}, {"role": "assistant", "content": answer}]
                st.rerun()

        caution = ai.get("caution") or "ราคาและโปรโมชันเปลี่ยนบ่อย ตรวจกับร้านค้าก่อนซื้อ"
        st.caption(caution + (f" ระบบตัดคำตอบของ AI ที่อ้างถึงรุ่นนอกรายการ {ai['dropped']} รายการ" if ai.get("dropped") else ""))

# ---------------------------------------------------------------------------
# แท็บ: เทียบเอง
# ---------------------------------------------------------------------------
with tab_compare:
    st.subheader("เลือก 2–3 รุ่นมาเทียบกัน")
    pool = phones[phones["in_thailand"]] if st.session_state.thailand_only else phones
    chosen = st.multiselect("รุ่นที่อยากเทียบ", sorted(pool["name"]), max_selections=3, key="compare_pick",
                            placeholder="พิมพ์ชื่อรุ่น เช่น Galaxy S26")
    if len(chosen) >= 2:
        scored = score(pool, Request(use_case=st.session_state.get("use_case") or "ใช้งานทั่วไป/เรียน"))
        sel = scored[scored["name"].isin(chosen)].set_index("name").loc[chosen].reset_index()
        st.plotly_chart(radar(sel, chosen), use_container_width=True, config={"displayModeBar": False})
        ui.html_block(compare_html(sel))
        st.caption("ตัวเลขสีเขียวคือดีที่สุดในกลุ่มที่เทียบ ราคาประมาณแปลงจากราคาอินเดีย ตรวจราคาไทยกับร้านก่อนซื้อ")
    else:
        st.markdown('<p class="note">เลือกอย่างน้อย 2 รุ่น</p>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# แท็บ: ดูทุกรุ่น
# ---------------------------------------------------------------------------
with tab_browse:
    st.subheader("ดูทุกรุ่น")
    f1, f2, f3 = st.columns([2, 1.4, 1.2])
    with f1:
        query = st.text_input("ค้นหารุ่น", key="browse_q", placeholder="เช่น iPhone, Galaxy A, Reno")
    with f2:
        browse_brands = st.multiselect("แบรนด์", sorted(phones["brand"].unique()), key="browse_brands",
                                       placeholder="ทุกแบรนด์")
    with f3:
        sort_by = st.selectbox("เรียงตาม", ["ราคาต่ำ → สูง", "ราคาสูง → ต่ำ", "แบตเตอรี่มากสุด", "กล้องละเอียดสุด"],
                               key="browse_sort")
    view = phones[phones["in_thailand"]] if st.session_state.thailand_only else phones
    if query:
        view = view[view["name"].str.contains(query.strip(), case=False, regex=False)]
    if browse_brands:
        view = view[view["brand"].isin(browse_brands)]
    order = {"ราคาต่ำ → สูง": ("price_thb", True), "ราคาสูง → ต่ำ": ("price_thb", False),
             "แบตเตอรี่มากสุด": ("battery_mah", False), "กล้องละเอียดสุด": ("camera_mp", False)}[sort_by]
    view = view.sort_values(order[0], ascending=order[1], na_position="last")
    scope = "รุ่นที่ขายในไทย" if st.session_state.thailand_only else "ทุกรุ่น"
    st.markdown(f'<p class="note">พบ {len(view)} รุ่น ({scope}) แสดงสูงสุด 60 รุ่น</p>', unsafe_allow_html=True)
    if view.empty:
        st.info("ไม่พบรุ่นที่ค้นหา ลองพิมพ์ชื่อสั้นลง หรือปิด “เฉพาะรุ่นที่ขายในไทย” ในแท็บหามือถือ")
    else:
        cards = []
        for _, r in view.head(60).iterrows():
            specs = [x for x in (spec_text(r, "performance"), spec_text(r, "storage"), spec_text(r, "camera"),
                                 spec_text(r, "battery")) if x]
            note = "ราคาไทย" if r["price_kind"] == "ราคาไทย" else "ราคาประมาณ"
            specs = ([r["segment"]] if r.get("segment") else []) + specs
            cards.append(ui.mini_card(r["name"], ui.baht(r["price_thb"]), note, specs, bool(r["in_thailand"]),
                                      ui.phone_image(r.get("image", ""), r["name"], r["brand"], small=True)))
        ui.html_block(ui.grid(cards))

# ---------------------------------------------------------------------------
# แท็บ: โมเดล ML
# ---------------------------------------------------------------------------
with tab_ml:
    rate = DEFAULT_INR_TO_THB
    pm, sg = price_model, segments
    st.subheader("1) ทำนาย “ราคาที่ควรเป็น” จากสเปก")
    st.markdown(f"Random Forest Regression เรียนรู้จากมือถือ {pm.n_train + pm.n_test} รุ่น ว่าสเปกแบบนี้ควรมีราคาเท่าไร "
                f"แบ่งข้อมูลสอน {pm.n_train} รุ่น และเก็บไว้ทดสอบ {pm.n_test} รุ่นที่โมเดลไม่เคยเห็น")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("R² (ยิ่งใกล้ 1 ยิ่งดี)", f"{pm.metrics['R2']:.2f}", delta=f"baseline {pm.baseline['R2']:.2f}", delta_color="off")
    m2.metric("คลาดเคลื่อนเฉลี่ย (MAE)", ui.baht(pm.metrics["MAE"] * rate),
              delta=f"baseline {ui.baht(pm.baseline['MAE'] * rate)}", delta_color="off")
    m3.metric("คลาดเคลื่อนเฉลี่ย (%)", f"{pm.metrics['MAPE']:.0f}%", delta=f"baseline {pm.baseline['MAPE']:.0f}%",
              delta_color="off")
    m4.metric("RMSE", ui.baht(pm.metrics["RMSE"] * rate), delta=f"baseline {ui.baht(pm.baseline['RMSE'] * rate)}",
              delta_color="off")
    st.caption("baseline คือการทายทุกรุ่นด้วยราคามัธยฐาน ใช้ดูว่าโมเดลเก่งกว่าการเดาแบบง่ายแค่ไหน "
               "ตัวเลขเงินบาทแปลงจากราคาอินเดีย")
    left, right = st.columns(2)
    with left:
        st.markdown("**ราคาจริง เทียบ ราคาที่ทาย (ชุดทดสอบ)**")
        st.plotly_chart(actual_vs_pred_chart(pm.test_pred, rate), use_container_width=True, config={"displayModeBar": False})
        st.caption("จุดยิ่งใกล้เส้นประ ยิ่งทายแม่น")
    with right:
        st.markdown("**อะไรทำให้มือถือแพง (Permutation Importance)**")
        st.plotly_chart(importance_chart(pm.importance), use_container_width=True, config={"displayModeBar": False})
        st.caption("วัดโดยสลับค่าทีละปัจจัยแบบสุ่ม แล้วดูว่าโมเดลทายแย่ลงเท่าไร ไม่ได้แปลว่าเป็นสาเหตุโดยตรง")

    st.markdown("**นำไปใช้:** ทุกรุ่นได้ “ราคาที่ควรเป็น” จากโมเดลที่ไม่เคยเห็นรุ่นนั้น (5-fold cross-validation) "
                "ถ้าราคาจริงต่ำกว่า 15% ขึ้นไปติดป้าย “ถูกกว่าสเปก” สูงกว่า 15% ติด “แพงกว่าสเปก” "
                "และใช้เป็นคะแนนความคุ้มค่าในการจัดอันดับ")
    pool = phones[phones["in_thailand"]] if st.session_state.thailand_only else phones
    deals = pool.dropna(subset=["deal_ratio"]).sort_values("deal_ratio")
    best, worst = deals.head(5), deals.tail(5).iloc[::-1]

    def deal_rows(d: pd.DataFrame) -> list:
        return [(r["name"], [ui.baht(r["price_thb"]), ui.baht(r["fair_price_thb"]), r["deal_label"]], None)
                for _, r in d.iterrows()]

    scope = "ที่ขายในไทย" if st.session_state.thailand_only else "ทั้งหมด"
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**คุ้มที่สุด 5 รุ่น ({scope})**")
        ui.html_block(ui.compare_table(["ราคา", "ควรเป็น", "สรุป"], deal_rows(best)))
    with c2:
        st.markdown(f"**แพงเกินสเปกที่สุด 5 รุ่น ({scope})**")
        ui.html_block(ui.compare_table(["ราคา", "ควรเป็น", "สรุป"], deal_rows(worst)))

    st.subheader("2) แบ่งกลุ่มมือถือด้วย K-Means")
    st.markdown(f"จัดกลุ่มจาก ประสิทธิภาพ RAM ความจุ กล้อง แบต ชาร์จ จอ และราคา (ปรับมาตรฐานก่อน) "
                f"ลองแบ่ง {min(sg.silhouette)}–{max(sg.silhouette)} กลุ่ม แล้วเลือก **{sg.k} กลุ่ม** ที่ได้ silhouette score สูงสุด "
                f"({sg.silhouette[sg.k]:.2f}) ชื่อกลุ่มตั้งอัตโนมัติจากระดับราคาและจุดเด่นของกลุ่ม")
    st.plotly_chart(segment_chart(sg.coords), use_container_width=True, config={"displayModeBar": False})
    st.caption("ย่อข้อมูล 8 มิติให้เหลือ 2 มิติด้วย PCA เพื่อวาดกราฟ จุดสีเดียวกันคือกลุ่มเดียวกัน")
    prof = sg.profile
    rows = [("จำนวนรุ่น", [f"{c:,}" for c in prof["count"]], None),
            ("ราคากลาง (บาท)", [ui.baht(v * rate) for v in prof["price_inr"]], None),
            ("ประสิทธิภาพชิปเฉลี่ย", [f"{v:.0f}/100" for v in prof["perf_score"]], None),
            ("RAM / ความจุ", [f"{a:.0f} / {b:.0f} GB" for a, b in zip(prof["ram_gb"], prof["storage_gb"])], None),
            ("กล้องหลัก", [f"{v:.0f} MP" for v in prof["camera_mp"]], None),
            ("แบต / ชาร์จ", [f"{a:,.0f} mAh / {b:.0f}W" for a, b in zip(prof["battery_mah"], prof["charging_w"])], None)]
    ui.html_block(ui.compare_table(list(prof["segment"]), rows))
    st.caption("ค่าในตารางเป็นค่ามัธยฐานของแต่ละกลุ่ม ป้ายกลุ่มแสดงบนการ์ดมือถือทุกใบ")

# ---------------------------------------------------------------------------
# แท็บ: วิธีคิดคะแนน
# ---------------------------------------------------------------------------
with tab_about:
    st.subheader("ระบบเลือกให้อย่างไร")
    st.markdown("""
1. **กรอง** ตามงบ แบรนด์ ความจุ 5G/NFC และเลือกได้ว่าจะดูเฉพาะรุ่นที่ขายอย่างเป็นทางการในไทย
2. **ให้คะแนนรายด้าน** ประสิทธิภาพ กล้องหลัก กล้องหน้า แบต ชาร์จเร็ว จอลื่น ความจุ RAM เป็น 0–100 โดยเทียบกับรุ่นอื่นในกลุ่ม
3. **ถ่วงน้ำหนักตามการใช้งาน** เช่น เล่นเกมเน้นประสิทธิภาพและจอ ถ่ายรูปเน้นกล้องและความจุ ด้านที่คุณเลือกเน้นจะได้น้ำหนักเพิ่ม
4. **คิดความคุ้มค่า** จากโมเดล Machine Learning ที่ทายราคาที่ควรเป็นจากสเปก (ดูแท็บ “โมเดล ML”) รุ่นที่ข้อมูลไม่ครบจะถูกลดคะแนนตามสัดส่วน
5. **ข้อดี/ข้อควรรู้** มาจากคะแนนรายด้าน (70 ขึ้นไป = เด่น, 30 ลงมา = ด้อย) อ้างตัวเลขจริง
6. **AI อธิบาย** เขียนเหตุผลจาก 5 รุ่นที่ระบบเลือกแล้วเท่านั้น ถ้า AI พูดถึงรุ่นอื่น ระบบจะตัดทิ้ง
""")
    st.subheader("ข้อควรรู้")
    st.markdown("""
- ราคาที่ระบุว่า “ราคาประมาณ” แปลงจากราคาขายในอินเดีย ไม่ใช่ราคาไทย ภาษีและโปรโมชันต่างกัน ตรวจกับร้านก่อนซื้อ
- คะแนนประสิทธิภาพประมาณจากชื่อชิป ไม่ใช่ผลทดสอบจริง
- จำนวนเมกะพิกเซลไม่ได้บอกคุณภาพภาพทั้งหมด ดูรีวิวประกอบ
- คะแนนเป็นการเทียบในกลุ่มที่ผ่านการกรอง เปลี่ยนงบแล้วคะแนนเปลี่ยนได้
""")
