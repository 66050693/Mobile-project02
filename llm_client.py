"""เรียก Groq Cloud (API แบบเดียวกับ OpenAI Chat Completions) ด้วย requests ไม่ต้องลง SDK เพิ่ม

- อ่าน GROQ_API_KEY / GROQ_MODEL จาก Streamlit Secrets หรือ .env
- ลองใหม่อัตโนมัติเมื่อเจอ 429 (เกินโควตาชั่วคราว) หรือ 5xx
- แปลง error เป็นข้อความภาษาไทยที่อ่านเข้าใจ (เช่น key ผิด)
"""
from __future__ import annotations

import time

import requests

from config import DEFAULT_GROQ_MODEL, secret

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
RETRY_DELAYS = (0, 2, 5)


class LLMError(RuntimeError):
    """error ที่ข้อความพร้อมแสดงให้ผู้ใช้"""


def has_key() -> bool:
    return bool(secret("GROQ_API_KEY"))


def model_name() -> str:
    return secret("GROQ_MODEL") or DEFAULT_GROQ_MODEL


def json_schema(schema):
    """แปลง schema แบบเดิม (type ตัวใหญ่ + nullable) เป็น JSON Schema มาตรฐาน"""
    if isinstance(schema, list):
        return [json_schema(x) for x in schema]
    if not isinstance(schema, dict):
        return schema
    out = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.lower()
        elif k == "nullable":
            continue
        else:
            out[k] = json_schema(v)
    if schema.get("nullable") and isinstance(out.get("type"), str):
        out["type"] = [out["type"], "null"]
    return out


def _friendly(status: int, body: str) -> str:
    if status == 401:
        return "GROQ_API_KEY ไม่ถูกต้องหรือถูกยกเลิก สร้าง key ใหม่ที่ console.groq.com/keys แล้วใส่ใน Secrets"
    if status == 429:
        return "ใช้ AI ถี่เกินโควตาฟรีของ Groq รอสักครู่แล้วลองใหม่"
    if status == 404 or "model" in body.lower() and status == 400:
        return f"ไม่พบโมเดล {model_name()} บน Groq ตรวจค่า GROQ_MODEL ({body[:120]})"
    return f"Groq ตอบกลับ {status}: {body[:160]}"


def complete(messages: list[dict], *, tools: list[dict] | None = None, json_mode: bool = False,
             temperature: float = 0.2, timeout: int = 60) -> dict:
    """คืน message ของคำตอบ {"role", "content", "tool_calls"?}"""
    key = secret("GROQ_API_KEY")
    if not key:
        raise LLMError("ยังไม่ได้ตั้งค่า GROQ_API_KEY")
    payload = {"model": model_name(), "messages": messages, "temperature": temperature}
    if tools:
        payload["tools"] = [{"type": "function", "function": t} for t in tools]
        payload["tool_choice"] = "auto"
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    last = "เรียก Groq ไม่สำเร็จ"
    for delay in RETRY_DELAYS:
        if delay:
            time.sleep(delay)
        try:
            r = requests.post(GROQ_URL, json=payload, timeout=timeout,
                              headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        except requests.RequestException as err:
            last = f"เชื่อมต่อ Groq ไม่ได้ ({err.__class__.__name__})"
            continue
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]
        last = _friendly(r.status_code, r.text)
        if r.status_code not in (429, 500, 502, 503, 504):
            break
    raise LLMError(last)
