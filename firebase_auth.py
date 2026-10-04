"""ล็อกอิน/สมัครสมาชิก/รีเซ็ตรหัสผ่านด้วย Firebase Authentication (REST API)"""
from __future__ import annotations

import requests

from config import flag, secret

FIREBASE_URL = "https://identitytoolkit.googleapis.com/v1"
MESSAGES = {
    "EMAIL_EXISTS": "อีเมลนี้สมัครไว้แล้ว",
    "EMAIL_NOT_FOUND": "ไม่พบอีเมลนี้",
    "INVALID_PASSWORD": "รหัสผ่านไม่ถูกต้อง",
    "INVALID_LOGIN_CREDENTIALS": "อีเมลหรือรหัสผ่านไม่ถูกต้อง",
    "INVALID_EMAIL": "รูปแบบอีเมลไม่ถูกต้อง",
    "MISSING_PASSWORD": "กรุณากรอกรหัสผ่าน",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "ลองผิดหลายครั้งเกินไป รอสักครู่แล้วลองใหม่",
    "USER_DISABLED": "บัญชีนี้ถูกระงับ",
    "OPERATION_NOT_ALLOWED": "ยังไม่ได้เปิด Email/Password ใน Firebase Authentication",
}


def get_firebase_key() -> str:
    return secret("FIREBASE_API_KEY")


def guest_allowed() -> bool:
    """โหมดทดสอบไม่ต้องล็อกอิน: ตั้ง ALLOW_GUEST=1 (ใช้ในเครื่องเท่านั้น)"""
    return flag("ALLOW_GUEST")


def _post(endpoint: str, payload: dict) -> dict:
    key = get_firebase_key()
    if not key:
        return {"ok": False, "message": "ยังไม่ได้ตั้งค่า FIREBASE_API_KEY (ดู README)"}
    try:
        response = requests.post(f"{FIREBASE_URL}/{endpoint}", params={"key": key}, json=payload, timeout=20)
        data = response.json()
    except requests.RequestException:
        return {"ok": False, "message": "เชื่อมต่อ Firebase ไม่ได้ ตรวจสอบอินเทอร์เน็ตแล้วลองใหม่"}
    except ValueError:
        return {"ok": False, "message": "Firebase ตอบกลับข้อมูลที่อ่านไม่ได้"}
    if response.ok:
        return {"ok": True, "email": data.get("email", payload.get("email")), "id_token": data.get("idToken"),
                "local_id": data.get("localId")}
    code = str(data.get("error", {}).get("message", "Firebase error"))
    if code.startswith("WEAK_PASSWORD"):
        return {"ok": False, "message": "รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร"}
    return {"ok": False, "message": MESSAGES.get(code.split(" ")[0], code)}


def register_user(email: str, password: str) -> dict:
    return _post("accounts:signUp", {"email": email.strip(), "password": password, "returnSecureToken": True})


def login_user(email: str, password: str) -> dict:
    return _post("accounts:signInWithPassword", {"email": email.strip(), "password": password, "returnSecureToken": True})


def reset_password(email: str) -> dict:
    r = _post("accounts:sendOobCode", {"requestType": "PASSWORD_RESET", "email": email.strip()})
    if r["ok"]:
        r["message"] = "ส่งลิงก์ตั้งรหัสผ่านใหม่ไปที่อีเมลแล้ว"
    return r
