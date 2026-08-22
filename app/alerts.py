import os
import time
import requests

TELEGRAM_BOT_TOKEN = "8647346721:AAESVq7LqJpNPPP6RS7qpFiRvbxk0mBA0VY"  # Paste token inside quotes
TELEGRAM_CHAT_ID = "8990682481"    # Paste ID inside quotes

def _send_telegram_alert(subject: str, text: str, snapshot_path: str | None) -> bool:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
        
    message_body = f"*{subject}*\n\n{text}"
    try:
        if snapshot_path and os.path.isfile(snapshot_path):
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
            with open(snapshot_path, "rb") as photo:
                payload = {"chat_id": TELEGRAM_CHAT_ID, "caption": message_body, "parse_mode": "Markdown"}
                requests.post(url, data=payload, files={"photo": photo}, timeout=10)
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message_body, "parse_mode": "Markdown"}
            requests.post(url, json=payload, timeout=10)
        return True
    except Exception as e:
        print(f"[TELEGRAM ERROR] {e}")
        return False

def send_alert(
    snapshot_path: str | None,
    confidence: float,
    camera_id: str,
    contacts: list,
    smtp_config: dict,
    gps: dict | None = None,
    test_mode: bool = False,
) -> dict:
    
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    mode_note = " [TEST]" if test_mode else ""
    conf_pct  = f"{confidence * 100:.1f}%"
    subject = f"🚨 ResQVision ALERT{mode_note} — Accident Detected"
    
    clean_text = f"Camera: {camera_id}\nTime: {timestamp}\nConfidence: {conf_pct}\n"
    
    success = _send_telegram_alert(subject, clean_text, snapshot_path if not test_mode else None)

    if success:
        return {"success": True, "error": None, "details": []}
    else:
        return {"success": False, "error": "Telegram dispatch failed. Check Bot Token/Chat ID.", "details": []}