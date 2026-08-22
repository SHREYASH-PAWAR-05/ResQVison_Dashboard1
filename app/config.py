"""
Configuration for ResQVision Dashboard.

Settings are persisted to data/settings.json so they survive restarts and can
be edited from the Settings panel in the UI without touching code.
"""
import json
import os
import threading

BASE_DIR      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SETTINGS_PATH = os.path.join(BASE_DIR, "data", "settings.json")
SNAPSHOTS_DIR = os.path.join(BASE_DIR, "snapshots")
DB_PATH       = os.path.join(BASE_DIR, "data", "resqvision.db")
DEFAULT_MODEL_PATH = os.path.join(BASE_DIR, "models", "best.pt")

DEFAULTS: dict = {
    # ---- video source --------------------------------------------------
    # "0" = default webcam, a file path, or an rtsp:// / http:// URL
    "video_source": "0",
    "model_path":   DEFAULT_MODEL_PATH,
    "camera_id":    "CAM-1",

    # ---- GPS (per-camera; shown as a Maps link in incident cards) ------
    "gps_location": {"lat": None, "lon": None},

    # ---- detection parameters -----------------------------------------
    "confidence_threshold":       0.5,
    # seconds to wait after logging an incident before another can fire
    "cooldown_seconds":           15,
    # detection box must cover at least this fraction of the frame area
    "min_box_area_ratio":         0.02,
    # how many consecutive frames must qualify before raising an incident
    "consecutive_frames_required": 5,

    # ---- alert channels -----------------------------------------------
    # smtp_* are the credentials used to *send* alerts
    "smtp_host":     "smtp.gmail.com",
    "smtp_port":     587,
    "smtp_user":     "",
    "smtp_password": "",
    "smtp_from":     "",   # leave blank to fall back to smtp_user

    # ---- emergency contacts -------------------------------------------
    # each entry: {name, email, phone, carrier, method}
    #   method  : "email" | "sms" | "both"
    #   carrier : key from alerts.CARRIER_GATEWAYS (for SMS-via-gateway)
    "emergency_contacts": [],
}

_lock = threading.RLock()   # RLock: save_settings() calls load_settings() internally


def _ensure_file():
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    if not os.path.exists(SETTINGS_PATH):
        with open(SETTINGS_PATH, "w") as f:
            json.dump(DEFAULTS, f, indent=2)


def load_settings() -> dict:
    _ensure_file()
    with _lock:
        with open(SETTINGS_PATH, "r") as f:
            data = json.load(f)
    # backfill any keys added in later versions of the app
    merged = {**DEFAULTS, **data}
    return merged


def save_settings(new_settings: dict) -> dict:
    _ensure_file()
    with _lock:
        current = load_settings()
        current.update(new_settings)
        with open(SETTINGS_PATH, "w") as f:
            json.dump(current, f, indent=2)
    return current
