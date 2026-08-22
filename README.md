# ResQVision Dashboard

A local control-room web dashboard for the ResQVision real-time accident
detection project. Watches a video feed with your fine-tuned YOLOv8 model,
overlays detections live, and — critically — never auto-sends alerts. Every
flagged incident waits for a human operator to **Confirm & Alert** or
**Dismiss as False Positive**.

## What's in this folder

```
resqvision_dashboard/
├── app/
│   ├── main.py        FastAPI app: routes, MJPEG stream, API
│   ├── detection.py    background thread: model + camera loop
│   ├── alerts.py        wraps the WhatsApp alert send (pywhatkit)
│   ├── db.py             SQLite incident storage
│   └── config.py       settings load/save (data/settings.json)
├── templates/
│   └── index.html       the single-page dashboard UI
├── static/
│   ├── style.css        control-room styling
│   └── app.js             frontend logic (tabs, polling, forms)
├── models/
│   └── best.pt              your trained YOLOv8 weights (already copied in)
├── data/                 settings.json + resqvision.db get created here
├── snapshots/            incident snapshot images get saved here
├── requirements.txt
├── run.py                    `python run.py` starts everything
└── README.md
```

## 1. Prerequisites

- Python 3.10+ (the code uses modern type hints)
- A webcam, video file, or RTSP stream to point the dashboard at
- For real alerts: a browser logged into **web.whatsapp.com** (pywhatkit
  automates that tab — see the note below)

## 2. Set up a virtual environment and install dependencies

```bash
cd resqvision_dashboard
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

`ultralytics` will pull in PyTorch, so this install can take a few minutes and
a few GB of disk — that's expected the first time.

## 3. Run it

```bash
python run.py
```

Then open **http://localhost:8000** in your browser.

On first launch, `data/settings.json` and `data/resqvision.db` are created
automatically with sensible defaults (webcam index `0`, `models/best.pt`,
confidence threshold `0.5`). Go to the **Settings** tab to point it at your
actual test video / webcam / RTSP source and add emergency contacts.

## 4. Using it

- **Live Monitor** — the live feed with detection boxes drawn on it, plus
  current status and FPS.
- **Incident Review** — this is the safety-critical screen. When the model is
  confident it's seen an accident, a pending incident appears here with its
  snapshot. Nothing is sent to anyone until you click **Confirm & Alert**.
  **Dismiss as False Positive** logs it with no alert.
- **Incident History** — every past incident (confirmed or dismissed), with
  timestamp, thumbnail, confidence, decision, and whether the alert actually
  sent successfully. Useful evidence for your report/viva.
- **Settings** — video source, model path, confidence threshold, cooldown
  between incidents, and the emergency contact list. Saving restarts the
  detection loop so changes take effect immediately.

## 5. Pointing it at a real CCTV feed (RTSP) or a test video

In the **Settings** tab, the "Source" field accepts three kinds of value:

| What you want          | What to put in the field                        |
|-------------------------|--------------------------------------------------|
| Your laptop's webcam    | `0` (or `1`, `2`... if you have more than one)   |
| A test video file       | Full path, e.g. `C:\Users\you\Videos\crash.mp4`  |
| A real CCTV stream      | The RTSP URL, e.g. `rtsp://user:pass@192.168.1.50:554/stream1` |

Get the RTSP URL from your CCTV's own admin page/manual — the exact path
(`/stream1`, `/Streaming/Channels/101`, etc.) varies by brand. Most DVRs/NVRs
also expose an HTTP MJPEG or ONVIF URL as an alternative if RTSP doesn't work.

If the CCTV connection drops mid-stream, the dashboard now automatically
tries to reconnect (with a short backoff) rather than stopping — useful for
real network cameras, which occasionally hiccup. A test video file, by
contrast, just loops back to the start when it ends, which is convenient for
repeated demo runs.

## 6. Reducing false positives (e.g. small/irrelevant objects flagged as accidents)

Two Settings-panel controls exist specifically for this:

- **Confidence threshold** — the obvious lever; raise it if you're getting
  low-confidence junk detections.
- **Minimum box size to count (% of frame area)** — a detection's box has to
  cover at least this fraction of the frame to count at all. This is what
  stops a small/irrelevant object from triggering an "accident" even if the
  model is confident about it — increase this if tiny objects are still
  getting flagged; decrease it if genuine accidents are being missed because
  they're far from the camera.
- **Consecutive frames required** — the detection has to hold up over this
  many frames in a row (not just one lucky/flickering frame) before it
  becomes a pending incident. Raise this for a stream with a lot of jitter;
  lower it if real accidents are being missed because they're brief.

These three work together and don't require retraining the model — they're
tuned entirely from the Settings tab and apply live on save. If you're still
seeing false positives after tuning these, that's a sign the model itself
needs more/better training data for that scenario (which your team already
has as ongoing work) — the dashboard can filter noise but can't fix an
under-trained model.

## 7. About the WhatsApp alert step (`pywhatkit`)

As called out in the project brief, `pywhatkit.sendwhats_image` works by
opening a real browser tab on **web.whatsapp.com** and driving it — it's a
placeholder integration, not a production alert channel. For it to work:

- You must already be logged into WhatsApp Web in your default browser.
- Don't touch the mouse/keyboard while it's sending (typically a ~20 second
  window per contact).
- If it's not installed, or fails, the dashboard still works — the incident
  gets marked "confirmed" and the History tab shows the alert as failed with
  the error message, rather than crashing.

If you swap this out for a different alert mechanism later, `app/alerts.py`
is the only file that needs to change — `send_alert()` is called from one
place in `app/main.py`.

## 8. Notes on how the detection loop is decoupled from review

The camera/model loop runs in its own background thread
(`app/detection.py`). It writes pending incidents straight to SQLite and
keeps reading frames — it never waits on the operator. The API layer polls
that same table, so a slow reviewer never blocks the video feed or causes
missed frames.

## 9. Known limitations (intentional, matches current project scope)

- No authentication — this is a single-machine, single-operator tool.
- No multi-camera support yet.
- No cloud deployment / Docker — run it locally as shown above.
- The alert channel is the placeholder WhatsApp automation described above,
  not a production-grade dispatch system.

## Troubleshooting

- **"Model weights not found"** — check the `model_path` in Settings points
  at a real `.pt` file (default is `models/best.pt`, already included).
- **"Could not open video source"** — for a webcam, try `0`, `1`, etc; for a
  file, use an absolute path; for RTSP, use the full `rtsp://` URL.
- **Feed looks frozen** — check the terminal running `python run.py` for
  errors; the Live Monitor's FPS readout will read `0.0` if the loop isn't
  running.
