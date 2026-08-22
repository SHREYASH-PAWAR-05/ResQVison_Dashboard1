"""
ResQVision Dashboard — FastAPI backend.

Run with:  python run.py
Then open: http://localhost:8000
"""
import os
import time
from datetime import datetime
from typing import Any

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, alerts
from .detection import engine

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="ResQVision Dashboard")

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.on_event("startup")
def on_startup():
    db.init_db()
    engine.start()


@app.on_event("shutdown")
def on_shutdown():
    engine.stop()


# ---------------------------------------------------------------- frontend --

@app.get("/")
def index():
    return FileResponse(os.path.join(BASE_DIR, "templates", "index.html"))


# ------------------------------------------------------------- video feed --

def _mjpeg_generator():
    boundary = b"--frame"
    while True:
        frame = engine.get_latest_jpeg()
        if frame is not None:
            yield (
                boundary + b"\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(0.033)   # ~30 fps cap on the streaming side


@app.get("/video_feed")
def video_feed():
    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/status")
def api_status():
    return engine.get_status()


# -------------------------------------------------------------- incidents --

@app.get("/api/incidents/pending")
def api_pending():
    return db.get_pending()


@app.get("/api/incidents/history")
def api_history():
    return db.get_history()


@app.get("/snapshots/{filename}")
def get_snapshot(filename: str):
    path = os.path.join(config.SNAPSHOTS_DIR, filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(path)


def _smtp_config_from_settings(settings: dict) -> dict:
    return {
        "smtp_host":     settings.get("smtp_host", "smtp.gmail.com"),
        "smtp_port":     settings.get("smtp_port", 587),
        "smtp_user":     settings.get("smtp_user", ""),
        "smtp_password": settings.get("smtp_password", ""),
        "smtp_from":     settings.get("smtp_from", "") or settings.get("smtp_user", ""),
    }


@app.post("/api/incidents/{incident_id}/confirm")
def confirm_incident(incident_id: int):
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] != "pending":
        raise HTTPException(status_code=400, detail="Incident already decided")

    settings      = config.load_settings()
    snapshot_path = os.path.join(config.SNAPSHOTS_DIR, incident["snapshot_path"])
    gps = {
        "lat": incident.get("gps_lat"),
        "lon": incident.get("gps_lon"),
    } if (incident.get("gps_lat") is not None) else None

    result = alerts.send_alert(
        snapshot_path = snapshot_path,
        confidence    = incident["confidence"],
        camera_id     = incident["camera_id"],
        contacts      = settings.get("emergency_contacts", []),
        smtp_config   = _smtp_config_from_settings(settings),
        gps           = gps,
    )

    db.decide_incident(
        incident_id,
        status     = "confirmed",
        decided_at = datetime.now().isoformat(timespec="seconds"),
        alert_sent = 1 if result["success"] else 0,
        alert_error = result.get("error"),
    )
    return {"incident_id": incident_id, "status": "confirmed", "alert_result": result}


@app.post("/api/incidents/{incident_id}/dismiss")
def dismiss_incident(incident_id: int):
    incident = db.get_incident(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    if incident["status"] != "pending":
        raise HTTPException(status_code=400, detail="Incident already decided")

    db.decide_incident(
        incident_id,
        status     = "dismissed",
        decided_at = datetime.now().isoformat(timespec="seconds"),
        alert_sent = None,
        alert_error = None,
    )
    return {"incident_id": incident_id, "status": "dismissed"}


# ------------------------------------------------------------ test alert ---

@app.post("/api/test-alert")
def test_alert():
    """Send a test alert to all configured emergency contacts (no real incident)."""
    settings = config.load_settings()
    contacts = settings.get("emergency_contacts", [])
    if not contacts:
        raise HTTPException(status_code=400, detail="No emergency contacts configured.")
    result = alerts.send_alert(
        snapshot_path = None,
        confidence    = 0.95,
        camera_id     = settings["camera_id"],
        contacts      = contacts,
        smtp_config   = _smtp_config_from_settings(settings),
        gps           = settings.get("gps_location"),
        test_mode     = True,
    )
    return result


# ---------------------------------------------------------------- settings --

class GpsLocation(BaseModel):
    lat: float | None = None
    lon: float | None = None


class SettingsUpdate(BaseModel):
    video_source:               str | None   = None
    model_path:                 str | None   = None
    confidence_threshold:       float | None = None
    cooldown_seconds:           float | None = None
    min_box_area_ratio:         float | None = None
    consecutive_frames_required: int | None  = None
    camera_id:                  str | None   = None
    gps_location:               dict | None  = None
    # alert / SMTP
    smtp_host:                  str | None   = None
    smtp_port:                  int | None   = None
    smtp_user:                  str | None   = None
    smtp_password:              str | None   = None
    smtp_from:                  str | None   = None
    # contacts
    emergency_contacts:         list | None  = None


@app.get("/api/settings")
def get_settings():
    s = config.load_settings()
    # Never send the SMTP password back to the client
    s["smtp_password"] = "••••••••" if s.get("smtp_password") else ""
    return s


@app.post("/api/settings")
def update_settings(update: SettingsUpdate, background_tasks: BackgroundTasks):
    payload = {k: v for k, v in update.model_dump().items() if v is not None}
    # Don't overwrite the real password if the client sent back our placeholder
    if payload.get("smtp_password") == "••••••••":
        payload.pop("smtp_password")
    new_settings = config.save_settings(payload)
    # Restart in background so the HTTP response returns immediately —
    # the engine's thread.join() would otherwise block for up to 5 seconds.
    background_tasks.add_task(engine.restart)
    new_settings["smtp_password"] = "••••••••" if new_settings.get("smtp_password") else ""
    return new_settings
