"""หน้าตาเว็บ: ธีม CSS และชิ้นส่วน UI ที่ใช้ซ้ำ

แนวคิด: "ป้ายราคาบนชั้นวางร้านมือถือ" พื้นเทาอลูมิเนียมสว่าง ตัวอักษรน้ำเงินเข้ม สีหลักน้ำเงินคราม
และใช้สีเหลืองป้ายราคาเพียงจุดเดียว คือราคาของรุ่นอันดับ 1 ฟอนต์ Anuphan (ไทย/อังกฤษในตระกูลเดียว)
"""
from __future__ import annotations

import html
import urllib.parse

import pandas as pd
import streamlit as st

INK = "#16203A"
MUTED = "#55607A"
LINE = "#DFE3EA"
SURFACE = "#FFFFFF"
PAGE = "#F3F5F8"
INDIGO = "#3A3FD9"
TAG = "#FFD23F"
GOOD = "#0E7A4F"
BAD = "#B4372F"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anuphan:wght@400;500;600;700&display=swap');
/* ฟอนต์: ใส่เฉพาะข้อความ ห้ามแตะ span ทั่วไป ไม่งั้นไอคอนจะกลายเป็นตัวหนังสือ เช่น "visibility" */
html, body, .stApp, p, li, label, input, textarea, button, h1, h2, h3, h4,
[data-testid="stMarkdownContainer"], [data-baseweb="tab"], [data-baseweb="select"] {{
  font-family: 'Anuphan', 'Noto Sans Thai', sans-serif;
}}
[data-testid="stIconMaterial"], .material-symbols-rounded, .material-icons {{
  font-family: 'Material Symbols Rounded', 'Material Icons' !important;
}}

/* บังคับโทนสว่างทั้งหน้า ให้หน้าตาเหมือนกันแม้เบราว์เซอร์หรือ Streamlit ตั้งเป็นธีมมืด */
.stApp, header[data-testid="stHeader"] {{ background: {PAGE}; color: {INK}; }}
.stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4,
[data-testid="stWidgetLabel"], [data-testid="stWidgetLabel"] p, [data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"], [data-testid="stMetricValue"], [data-testid="stMetricLabel"],
[data-testid="stExpander"] summary, [data-testid="stCheckbox"] label {{ color: {INK}; }}
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {{ color: {MUTED}; }}
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {{ background: {SURFACE}; }}
[data-testid="stSidebar"] {{ border-right: 1px solid {LINE}; }}
input, textarea, [data-baseweb="input"], [data-baseweb="base-input"], [data-baseweb="textarea"],
[data-baseweb="select"] > div, [data-testid="stNumberInputContainer"] {{
  background: {SURFACE} !important; color: {INK} !important; border-color: {LINE} !important; }}
input::placeholder, textarea::placeholder {{ color: #8A93A8 !important; }}
[data-testid="stNumberInputContainer"] button {{ background: {PAGE}; color: {INK}; }}
[data-baseweb="tab-list"] {{ gap: .4rem; border-bottom: 1px solid {LINE}; }}
[data-baseweb="tab"] {{ color: {MUTED}; }}
[data-baseweb="tab"][aria-selected="true"] {{ color: {INDIGO}; }}
[data-baseweb="tab-highlight"] {{ background: {INDIGO}; }}

.block-container {{ max-width: 1120px; padding-top: 4.5rem; }}
h1, h2, h3 {{ letter-spacing: -0.01em; }}
[data-testid="stVerticalBlockBorderWrapper"] {{ background: {SURFACE}; border-color: {LINE} !important; border-radius: 14px; }}

/* ปุ่ม: หลัก = น้ำเงินคราม (รวมปุ่มในฟอร์ม), รอง = ขาวขอบเทา */
button[kind="primary"], button[kind="primaryFormSubmit"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {INDIGO} !important; border-color: {INDIGO} !important; color: #fff !important; font-weight: 600; }}
button[kind="primary"] p, [data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primaryFormSubmit"] p {{ color: #fff !important; }}
button[kind="secondary"], button[kind="secondaryFormSubmit"], [data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondaryFormSubmit"], [data-testid="stBaseLinkButton-secondary"] {{
  background: {SURFACE} !important; color: {INK} !important; border: 1px solid {LINE} !important; }}
/* ปุ่มเม็ดยา (st.pills) */
[data-testid="stBaseButton-pills"] {{ background: {SURFACE} !important; color: {INK} !important; border: 1px solid {LINE} !important; }}
[data-testid="stBaseButton-pillsActive"] {{ background: #ECEDFC !important; color: {INDIGO} !important;
  border: 1px solid {INDIGO} !important; font-weight: 600; }}
[data-testid="stBaseButton-pills"] p, [data-testid="stBaseButton-pillsActive"] p {{ color: inherit !important; }}
button:focus-visible, a:focus-visible {{ outline: 3px solid {TAG} !important; outline-offset: 2px; }}
.stApp a {{ color: {INDIGO}; }}

.hero h1 {{ font-size: clamp(1.9rem, 4vw, 2.7rem); line-height: 1.15; margin: 0 0 .35rem; font-weight: 700; }}
.hero p {{ color: {MUTED}; font-size: 1.05rem; margin: 0 0 1.2rem; max-width: 62ch; }}

.rank {{ display: inline-flex; align-items: center; justify-content: center; width: 2rem; height: 2rem;
  border-radius: 50%; background: {INK}; color: #fff; font-weight: 700; margin-right: .6rem; flex: none; }}
.rank.first {{ background: {INDIGO}; }}
.pick-head {{ display: flex; align-items: center; gap: .2rem; }}
.pick-name {{ font-size: 1.35rem; font-weight: 700; color: {INK}; margin: 0; line-height: 1.25; }}
.pick-sub {{ color: {MUTED}; font-size: .92rem; margin: .15rem 0 0 2.6rem; }}

.price {{ text-align: right; }}
.price .amount {{ font-size: 1.6rem; font-weight: 700; color: {INK}; line-height: 1.1; }}
.price .kind {{ font-size: .8rem; color: {MUTED}; }}
.price.tag .amount {{ display: inline-block; background: {TAG}; padding: .25rem .75rem .3rem 1.4rem; border-radius: 6px;
  position: relative; }}
.price.tag .amount::before {{ content: ""; position: absolute; left: .55rem; top: 50%; width: 7px; height: 7px;
  margin-top: -3.5px; border-radius: 50%; background: {SURFACE}; box-shadow: inset 0 0 0 1px rgba(22,32,58,.35); }}

.meter {{ height: 8px; background: #E8EBF1; border-radius: 99px; overflow: hidden; margin: .55rem 0 .2rem; }}
.meter > span {{ display: block; height: 100%; background: {INDIGO}; border-radius: 99px; }}
.meter-label {{ font-size: .85rem; color: {MUTED}; }}

.chips {{ display: flex; flex-wrap: wrap; gap: .35rem; margin: .3rem 0 .2rem; }}
.chip {{ font-size: .84rem; padding: .18rem .6rem; border-radius: 99px; border: 1px solid {LINE}; background: {PAGE}; color: {INK}; }}
.chip.good {{ border-color: #BFE3D2; background: #EEF8F3; color: {GOOD}; }}
.chip.bad {{ border-color: #F0C9C5; background: #FCF1F0; color: {BAD}; }}
.why {{ margin: .6rem 0 .3rem; font-size: 1rem; line-height: 1.6; max-width: 75ch; }}
.list-title {{ font-weight: 600; font-size: .92rem; margin-top: .5rem; }}
.summary {{ border-left: 4px solid {INDIGO}; background: {SURFACE}; padding: .9rem 1.1rem; border-radius: 0 12px 12px 0;
  margin: .4rem 0 1rem; line-height: 1.6; }}
.note {{ color: {MUTED}; font-size: .86rem; }}
/* ตารางเทียบรุ่น */
.cmp {{ width: 100%; border-collapse: collapse; background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px;
  overflow: hidden; font-size: .95rem; }}
.cmp th, .cmp td {{ padding: .6rem .8rem; border-bottom: 1px solid {LINE}; text-align: left; vertical-align: top;
  line-height: 1.45; white-space: normal; }}
.cmp thead th {{ background: {PAGE}; font-weight: 700; color: {INK}; }}
.cmp tbody th {{ color: {MUTED}; font-weight: 500; width: 26%; }}
.cmp td.best {{ color: {GOOD}; font-weight: 700; }}
.cmp tr:last-child th, .cmp tr:last-child td {{ border-bottom: 0; }}
.cmp-wrap {{ overflow-x: auto; margin: .4rem 0 1rem; }}

/* การ์ดรุ่นในหน้าดูทุกรุ่น */
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: .8rem; margin-top: .6rem; }}
.mini {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 12px; padding: .9rem 1rem; display: flex;
  flex-direction: column; gap: .3rem; }}
.mini .n {{ font-weight: 700; font-size: 1.05rem; color: {INK}; line-height: 1.3; }}
.mini .p {{ font-weight: 700; font-size: 1.15rem; color: {INDIGO}; }}
.mini .k {{ font-size: .78rem; color: {MUTED}; }}
.mini .chips {{ margin: .2rem 0 0; }}
.mini .chip {{ font-size: .78rem; padding: .1rem .5rem; }}
.flag {{ font-size: .75rem; color: {GOOD}; font-weight: 600; }}
/* รูปมือถือ */
.phone-img {{ width: 100%; max-width: 132px; aspect-ratio: 4 / 5; border-radius: 12px; background: {PAGE};
  border: 1px solid {LINE}; display: flex; align-items: center; justify-content: center; overflow: hidden; }}
.phone-img img {{ width: 100%; height: 100%; object-fit: contain; }}
.phone-img svg {{ height: 72%; width: auto; }}
.phone-img.sm {{ max-width: none; aspect-ratio: 16 / 10; margin-bottom: .2rem; }}
.upgrade {{ background: {SURFACE}; border: 1px dashed {INDIGO}; border-radius: 12px; padding: .8rem 1rem; margin: .4rem 0; }}
.upgrade b {{ color: {INDIGO}; }}
.reason-list {{ margin: .3rem 0 0 1.1rem; line-height: 1.7; }}
@media (max-width: 640px) {{
  .pick-sub {{ margin-left: 0; }} .price {{ text-align: left; margin-top: .4rem; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def apply_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""))


def baht(x) -> str:
    return "—" if x is None or pd.isna(x) else f"฿{x:,.0f}"


def hero(title: str, subtitle: str) -> None:
    st.markdown(f'<div class="hero"><h1>{esc(title)}</h1><p>{esc(subtitle)}</p></div>', unsafe_allow_html=True)


def pick_header(rank: int, name: str, sub: str) -> str:
    first = " first" if rank == 1 else ""
    return (f'<div class="pick-head"><span class="rank{first}">{rank}</span><p class="pick-name">{esc(name)}</p></div>'
            f'<p class="pick-sub">{esc(sub)}</p>')


def price_block(price, kind: str, highlight: bool) -> str:
    label = "ราคาไทย" if kind == "ราคาไทย" else "ราคาประมาณ (แปลงจากราคาอินเดีย)"
    cls = "price tag" if highlight else "price"
    return f'<div class="{cls}"><div class="amount">{baht(price)}</div><div class="kind">{esc(label)}</div></div>'


def meter(score, label: str = "ความเหมาะสม") -> str:
    v = 0 if score is None or pd.isna(score) else float(score)
    return (f'<div class="meter" role="img" aria-label="{esc(label)} {v:.0f} จาก 100"><span style="width:{v:.0f}%"></span></div>'
            f'<div class="meter-label">{esc(label)} {v:.0f}/100</div>')


def chips(items: list[str], kind: str = "") -> str:
    if not items:
        return ""
    return '<div class="chips">' + "".join(f'<span class="chip {kind}">{esc(i)}</span>' for i in items) + "</div>"


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def pills(label: str, options: list[str], *, multi: bool, default, key: str, format_func=None):
    """ปุ่มเลือกแบบเม็ดยา (st.pills) ถ้า Streamlit รุ่นเก่าไม่มี ใช้ selectbox/multiselect แทน

    ค่าเริ่มต้นเก็บใน session_state[key] (ไม่ส่ง default ให้ widget ซ้ำ เพื่อไม่ให้ Streamlit เตือน)
    """
    fmt = format_func or (lambda x: x)
    st.session_state.setdefault(key, default)
    if hasattr(st, "pills"):
        value = st.pills(label, options, selection_mode="multi" if multi else "single", key=key, format_func=fmt)
        if not multi and value is None:  # กดยกเลิกการเลือก ใช้ค่าเริ่มต้นแทน
            return default
        return value or []
    if multi:
        return st.multiselect(label, options, key=key, format_func=fmt)
    return st.selectbox(label, options, key=key, format_func=fmt)


def compare_table(columns: list[str], rows: list[tuple[str, list[str], int | None]]) -> str:
    """ตาราง HTML เทียบรุ่น: rows = [(หัวข้อ, [ค่าแต่ละรุ่น], index ของค่าที่ดีที่สุดหรือ None)]"""
    head = "".join(f"<th scope='col'>{esc(c)}</th>" for c in columns)
    body = ""
    for label, values, best in rows:
        cells = "".join(f"<td class='best'>{esc(v)}</td>" if i == best else f"<td>{esc(v)}</td>" for i, v in enumerate(values))
        body += f"<tr><th scope='row'>{esc(label)}</th>{cells}</tr>"
    return f"<div class='cmp-wrap'><table class='cmp'><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def mini_card(name: str, price: str, price_note: str, specs: list[str], thai: bool, image: str = "") -> str:
    flag = "<span class='flag'>ขายในไทย</span>" if thai else ""
    return (f"<div class='mini'>{image}{flag}<div class='n'>{esc(name)}</div><div class='p'>{esc(price)}</div>"
            f"<div class='k'>{esc(price_note)}</div>{chips(specs)}</div>")


def grid(cards: list[str]) -> str:
    return "<div class='grid'>" + "".join(cards) + "</div>"


def _placeholder_svg(brand: str) -> str:
    """รูปสำรองเมื่อยังไม่มีรูปจริง: โครงมือถือเรียบๆ กับตัวย่อแบรนด์"""
    initials = esc((brand or "?")[:2].upper())
    return (f"<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 100' width='62%' role='img' aria-label='ยังไม่มีรูป {esc(brand)}'>"
            f"<rect x='18' y='6' width='44' height='88' rx='9' fill='#fff' stroke='{LINE}' stroke-width='2'/>"
            f"<rect x='34' y='11' width='12' height='3' rx='1.5' fill='{LINE}'/>"
            f"<text x='40' y='56' text-anchor='middle' font-size='14' font-weight='700' fill='{MUTED}' "
            f"font-family='Anuphan, sans-serif'>{initials}</text></svg>")


def phone_image(url: str, name: str, brand: str, small: bool = False) -> str:
    cls = "phone-img sm" if small else "phone-img"
    if isinstance(url, str) and url.startswith("http"):
        # ซ้อนพื้นหลัง 2 ชั้น: รูปจริงอยู่บน รูปสำรองอยู่ล่าง ถ้าลิงก์รูปเสีย ชั้นบนจะโปร่งใสและเห็นรูปสำรองแทน (ไม่ต้องใช้ JavaScript)
        fallback = "data:image/svg+xml;utf8," + urllib.parse.quote(_placeholder_svg(brand).replace("width='62%'", ""))
        safe_url = url.replace("'", "%27").replace('"', "%22").replace(")", "%29").replace("(", "%28")
        style = (f"background-image:url('{esc(safe_url)}'),url('{fallback}');background-size:contain,auto 70%;"
                 "background-position:center;background-repeat:no-repeat;background-color:#fff")
        return f"<div class='{cls}' role='img' aria-label='{esc(name)}' style=\"{style}\"></div>"
    return f"<div class='{cls}'>{_placeholder_svg(brand)}</div>"
