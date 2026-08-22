"""
ResQVision Autonomous Detection Engine
Runs YOLOv8 model, monitors frames, and immediately triggers alerts.
Optimized for low latency and automatic GPU/CPU routing.
"""
import os
import threading
import time
from datetime import datetime
import cv2
import torch

from . import config, db, alerts

try:
    from ultralytics import YOLO
    ULTRALYTICS_AVAILABLE = True
except Exception:
    ULTRALYTICS_AVAILABLE = False


class DetectionEngine:
    def __init__(self):
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        self._model = None
        self._model_path = None

        self._latest_jpeg = None          # bytes, for MJPEG streaming
        self._latest_frame_lock = threading.Lock()

        self._fps = 0.0
        self._status_message = "Stopped"
        self._running = False
        self._last_error = None
        self._start_time: float | None = None
        self._last_incident_time = 0.0

        # Consecutive-frame confirmation state
        self._streak_count = 0
        self._streak_best_conf = 0.0
        self._streak_best_frame = None

    # ---------- Public API -------------------------------------------------

    def start(self):
        with self._lock:
            if self._running:
                return
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._running = True
            self._start_time = time.time()
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            self._stop_event.set()
            self._running = False
            with self._latest_frame_lock:
                self._latest_jpeg = None

    def restart(self):
        self.stop()
        old_thread = self._thread
        if old_thread is not None and old_thread.is_alive():
            old_thread.join(timeout=5.0)
        self._thread = None
        self.start()

    def is_running(self):
        return self._running

    def get_uptime(self) -> float:
        if self._start_time and self._running:
            return time.time() - self._start_time
        return 0.0

    def get_status(self):
        if not self._running:
            state = "stopped"
            message = self._last_error or "Monitoring stopped"
        else:
            state = "ok"
            message = "Monitoring Active"

        return {
            "state": state,
            "message": message,
            "fps": round(self._fps, 1),
            "pending_count": 0,
            "uptime": round(self.get_uptime()),
            "today_count": db.count_today(),
        }

    def get_latest_jpeg(self):
        with self._latest_frame_lock:
            return self._latest_jpeg

    # ---------- Internals --------------------------------------------------

    def _load_model(self, model_path):
        if not ULTRALYTICS_AVAILABLE:
            raise RuntimeError(
                "The 'ultralytics' package is not installed. "
                "Run `pip install ultralytics` in the project venv."
            )
        if not os.path.exists(model_path):
            raise RuntimeError(f"Model weights not found at: {model_path}")
        
        model = YOLO(model_path)
        
        # FORCE CPU: Prevents VRAM overflow on 2GB MX330 GPU to fix the 1 FPS lag
        model.to("cpu")
        print("[ENGINE] Running on CPU (forced to preserve memory).")
        
        return model

    def _normalize_source(self, source_str: str):
        s = source_str.strip()
        if s.lstrip("-").isdigit():
            return int(s)
        return s

    def _is_live_source(self, source_str: str) -> bool:
        source = self._normalize_source(source_str)
        if isinstance(source, int):
            return True
        return str(source).lower().startswith(("rtsp://", "http://", "https://"))

    def _open_source(self, source_str: str):
        source = self._normalize_source(source_str)
        cap = cv2.VideoCapture(source)
        if isinstance(source, str) and source.lower().startswith("rtsp://"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _run_loop(self):
        settings = config.load_settings()
        try:
            self._model = self._load_model(settings["model_path"])
        except Exception as e:
            self._last_error = str(e)
            self._running = False
            return

        video_source = settings["video_source"]
        is_live = self._is_live_source(video_source)

        cap = self._open_source(video_source)
        if not cap.isOpened():
            self._last_error = f"Could not open video source: {video_source}"
            self._running = False
            return

        self._last_error = None
        frame_count = 0
        fps_timer = time.time()
        consecutive_fails = 0
        self._streak_count = 0
        self._streak_best_conf = 0.0
        self._streak_best_frame = None

        os.makedirs(config.SNAPSHOTS_DIR, exist_ok=True)

        while not self._stop_event.is_set():
            ok, frame = cap.read()

            # Local file loop
            if (not ok or frame is None) and not is_live:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()

            # Failed read
            if not ok or frame is None:
                consecutive_fails += 1
                if is_live:
                    self._last_error = f"Reconnecting to: {video_source}"
                    cap.release()
                    time.sleep(min(1.0 + 0.5 * consecutive_fails, 5.0))
                    cap = self._open_source(video_source)
                    if not cap.isOpened():
                        self._last_error = f"Lost connection to: {video_source} (retrying)"
                else:
                    time.sleep(0.2)

                if consecutive_fails > 50:
                    self._last_error = f"Could not read from video source: {video_source}"
                    self._running = False
                    cap.release()
                    return
                continue

            consecutive_fails = 0

            # Dynamic settings
            settings = config.load_settings()
            conf_threshold = float(settings.get("confidence_threshold", 0.5))
            cooldown = float(settings.get("cooldown_seconds", 15))
            min_box_area_ratio = float(settings.get("min_box_area_ratio", 0.0))
            frames_required = max(1, int(settings.get("consecutive_frames_required", 1)))
            camera_id = settings.get("camera_id", "CAM-1")
            gps = settings.get("gps_location", {})
            gps_lat = gps.get("lat") if gps else None
            gps_lon = gps.get("lon") if gps else None

            # FORCED CPU INFERENCE: Keeps the required 1280 resolution without crashing the MX330 GPU
            results = self._model.predict(
                frame,
                verbose=False,
                conf=conf_threshold,
                imgsz=1280,
                device="cpu"
            )
            
            result = results[0]
            annotated = result.plot()

            frame_area = frame.shape[0] * frame.shape[1]
            qualifying_conf = 0.0
            if result.boxes is not None and len(result.boxes) > 0:
                xyxy = result.boxes.xyxy.cpu().numpy()
                confs = result.boxes.conf.cpu().numpy()
                for (x1, y1, x2, y2), c in zip(xyxy, confs):
                    box_area = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
                    if c >= conf_threshold and (box_area / frame_area) >= min_box_area_ratio:
                        qualifying_conf = max(qualifying_conf, float(c))

            success, buf = cv2.imencode(".jpg", annotated)
            if success:
                with self._latest_frame_lock:
                    self._latest_jpeg = buf.tobytes()

            if qualifying_conf > 0:
                self._streak_count += 1
                if qualifying_conf > self._streak_best_conf:
                    self._streak_best_conf = qualifying_conf
                    self._streak_best_frame = annotated
            else:
                self._streak_count = 0
                self._streak_best_conf = 0.0
                self._streak_best_frame = None

            now = time.time()
            if (
                self._streak_count >= frames_required
                and (now - self._last_incident_time) >= cooldown
            ):
                self._last_incident_time = now
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                snapshot_name = f"incident_{timestamp}.jpg"
                snapshot_path = os.path.join(config.SNAPSHOTS_DIR, snapshot_name)
                
                # Save snapshot
                save_frame = self._streak_best_frame if self._streak_best_frame is not None else annotated
                cv2.imwrite(snapshot_path, save_frame)

                print(f"🚨 [ACCIDENT CONFIRMED ({self._streak_best_conf*100:.1f}%)] Auto-dispatching alerts...")

                # 1. Store in SQLite DB
                incident_id = db.create_incident(
                    created_at=datetime.now().isoformat(timespec="seconds"),
                    camera_id=camera_id,
                    confidence=self._streak_best_conf,
                    snapshot_path=snapshot_name,
                    gps_lat=gps_lat,
                    gps_lon=gps_lon,
                    status="confirmed"
                )

                # 2. Dispatch Alert immediately
                contacts = settings.get("emergency_contacts", [])
                smtp_config = {
                    "smtp_host": settings.get("smtp_host", "smtp.gmail.com"),
                    "smtp_port": settings.get("smtp_port", 587),
                    "smtp_user": settings.get("smtp_user", ""),
                    "smtp_password": settings.get("smtp_password", ""),
                    "smtp_from": settings.get("smtp_from", "") or settings.get("smtp_user", ""),
                }
                gps_dict = {"lat": gps_lat, "lon": gps_lon} if gps_lat is not None else None

                alert_result = alerts.send_alert(
                    snapshot_path=snapshot_path,
                    confidence=self._streak_best_conf,
                    camera_id=camera_id,
                    contacts=contacts,
                    smtp_config=smtp_config,
                    gps=gps_dict,
                )

                # 3. Update DB Record
                db.decide_incident(
                    incident_id=incident_id,
                    status="confirmed",
                    decided_at=datetime.now().isoformat(timespec="seconds"),
                    alert_sent=1 if alert_result.get("success") else 0,
                    alert_error=alert_result.get("error"),
                )

                # Reset streak counter
                self._streak_count = 0
                self._streak_best_conf = 0.0
                self._streak_best_frame = None

            frame_count += 1
            elapsed = time.time() - fps_timer
            if elapsed >= 1.0:
                self._fps = frame_count / elapsed
                frame_count = 0
                fps_timer = time.time()

        cap.release()


engine = DetectionEngine()