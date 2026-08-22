# ResQVision — Web Dashboard Build Brief

## Project context (read this first)

ResQVision is a final-year undergraduate Computer Science (Data Science) project by a
5-person team. It's a real-time road accident detection system: a fine-tuned YOLOv8
model watches a CCTV/video feed, detects accidents, and should alert emergency
contacts with a snapshot.

**What already exists:**
- A fine-tuned YOLOv8 object detection model, single class (`Accident`), trained with
  Ultralytics. Weights file: `best.pt`.
- A working Python pipeline script (`resqvision_pipeline.py`) that: loads the model,
  reads frames from a video/camera source via OpenCV, runs detection each frame,
  saves an annotated snapshot on a confident detection (with a cooldown to avoid
  spamming), and sends a WhatsApp alert with the snapshot via `pywhatkit`.
- The team is currently still improving the model's accuracy (fine-tuning, testing at
  different image resolutions, etc.) — that work is separate and ongoing.

**Known limitations to be aware of, carried over from earlier discussion:**
- `pywhatkit` automates a real browser tab and requires no keyboard/mouse
  interference during send — it's a placeholder for a proper alert mechanism, not
  production-grade. It may get replaced later; the dashboard shouldn't assume a
  specific alert-sending method is final.
- **Critical design decision, must be reflected in the UI:** detections should NOT
  auto-dispatch alerts to real emergency contacts. A human operator must review and
  confirm a detected incident before any alert is sent. This exists because false
  positives triggering real alerts to police/ambulance is a genuine liability concern,
  not just a technical nice-to-have. The dashboard's core job is to be that human
  review point.

## What to build: a local web dashboard

**Purpose:** a control-room-style interface where an operator watches a live feed,
sees the model's detections overlaid in real time, and reviews/confirms or dismisses
each flagged incident before any alert goes out. This is both the actual deliverable
and the demo centerpiece for the project.

**This runs locally** on the team's own laptop/PC during development and for the
final demo — not deployed to any cloud service. Design for that (no need for
authentication systems, multi-tenancy, or public-facing security hardening — this is
a single-machine, single-operator tool for now).

### Suggested tech stack

- **Backend:** Python, FastAPI (integrates naturally with the existing Ultralytics/
  OpenCV pipeline code, async-friendly for streaming).
- **Frontend:** keep it simple — plain HTML/CSS/JS or a lightweight approach is fine;
  this doesn't need a heavy framework. Prioritize working and clear over polished.
- **Video streaming to the browser:** MJPEG stream over HTTP is the simplest reliable
  approach for this scale (single feed, local network) — avoids the complexity of
  WebRTC for what's needed here.
- **Data persistence:** SQLite. No need for a full database server — this is a
  single-machine app, SQLite's simplicity fits the scope.
- **Detection overlay:** draw bounding boxes server-side onto frames before streaming
  (simplest), OR stream raw frames and send box coordinates via a WebSocket/polling
  endpoint for client-side drawing (more flexible if the UI needs to highlight boxes
  interactively). Either is acceptable — pick whichever is faster to implement well.

### Required screens/features

1. **Live Monitor view (main screen)**
   - Shows the live video feed with detection boxes drawn on frames where the model
     is confident.
   - Shows current status (e.g., "Monitoring — no incidents" / "Incident detected,
     awaiting review").
   - Shows basic feed info: source name/camera ID, current FPS if easy to compute.

2. **Incident Review panel** (this is the core safety feature — the human-in-the-loop
   step described above)
   - When the model flags a potential accident, it should NOT immediately alert
     anyone. Instead, it creates a pending "incident" record: snapshot image,
     timestamp, confidence score.
   - The operator sees this pending incident with the snapshot and two actions:
     **"Confirm & Alert"** (sends the alert — reuse/wrap the existing alert-sending
     logic from `resqvision_pipeline.py`) or **"Dismiss as False Positive"** (logs it,
     no alert sent).
   - This is the single most important UX flow in the whole dashboard — make it fast
     and unambiguous for the operator to use under time pressure.

3. **Incident History / Log**
   - A list/table of all past incidents (confirmed and dismissed), each showing:
     timestamp, snapshot thumbnail, confidence score, operator's decision
     (confirmed/dismissed), and if confirmed, whether the alert send succeeded.
   - This log is valuable both as a real feature and as evidence for the project
     report/viva — it's a record showing the system works and shows good judgement
     was exercised (not blind auto-dispatch).

4. **Settings panel**
   - Video source configuration: file path, webcam index, or RTSP URL.
   - Confidence threshold slider/input (matches the `confidence_threshold` concept
     already used in `resqvision_pipeline.py`'s `Config`).
   - Emergency contact list management (name + number pairs) — reuse the existing
     `emergency_contacts` concept from the pipeline's config.

### Integration notes

- Don't rewrite the detection/alert logic from scratch — wrap and reuse the existing
  `resqvision_pipeline.py` code (model loading, frame processing loop, alert sending
  function). The dashboard's job is to add a web UI and the human-confirmation step
  around that existing logic, not replace it.
- The model file path and video source should be configurable from the Settings
  panel, not hardcoded, since the team will be testing with different model versions
  (fine-tuning is still ongoing) and different video sources (test files now, live
  webcam/CCTV later).
- Keep the incident review step decoupled from the detection loop itself (e.g., via a
  queue or a simple polling database check) so a slow operator response doesn't block
  the video processing loop from continuing to watch for new incidents.

### What NOT to build right now (out of scope, don't over-engineer)

- No user authentication/login system — single local operator, not needed.
- No cloud deployment, Docker, or CI/CD — this runs locally for now.
- No multi-camera support yet — single feed is enough for the current milestone;
  design reasonably extensibly but don't build the complexity now.
- No real "nearest emergency service" routing/GIS logic — the contact list is a
  simple manually configured list for this stage.

## Deliverable

A working local web app (`localhost`), startable with a single command, that
demonstrates the full loop: live feed → detection → pending incident → operator
review → confirm-and-alert (or dismiss) → logged in history. This should be
demoable end-to-end for a project viva.
