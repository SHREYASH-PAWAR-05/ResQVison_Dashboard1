// ResQVision Dashboard — frontend logic. Vanilla JS, no build step.
// Fully Automated Autonomous Version
"use strict";

// ================================================================ TOAST SYSTEM
const TOAST_ICONS = { success: "✅", error: "❌", info: "ℹ️", warning: "⚠️" };

function toast(message, type = "info", duration = 4000) {
  const container = document.getElementById("toast-container");
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="toast-icon">${TOAST_ICONS[type] ?? "ℹ️"}</span><span class="toast-msg">${message}</span>`;
  container.appendChild(el);

  const dismiss = () => {
    el.classList.add("leaving");
    el.addEventListener("animationend", () => el.remove(), { once: true });
  };
  const timer = setTimeout(dismiss, duration);
  el.addEventListener("click", () => { clearTimeout(timer); dismiss(); });
}

// ================================================================ CLOCK
function updateClock() {
  const now = new Date();
  document.getElementById("live-clock").textContent =
    now.toLocaleTimeString("en-GB", { hour12: false });
  document.getElementById("live-date").textContent =
    now.toLocaleDateString("en-GB", { weekday: "short", year: "numeric", month: "short", day: "numeric" });
}
setInterval(updateClock, 1000);
updateClock();

// ================================================================ TABS
function switchTab(name) {
  document.querySelectorAll(".tab-btn").forEach(b => {
    const isActive = b.dataset.tab === name;
    b.classList.toggle("active", isActive);
    b.setAttribute("aria-selected", isActive);
  });
  document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
  document.getElementById(`tab-${name}`).classList.add("active");

  if (name === "history")  loadHistory();
  if (name === "settings") loadSettings();
}

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => switchTab(btn.dataset.tab));
});
window.switchTab = switchTab;

// ================================================================ STATUS POLL
let lastIncidentCount = 0;

async function pollStatus() {
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();

    const dot = document.getElementById("status-dot");
    dot.className = "status-dot " + (data.state === "stopped" ? "stopped" : "ok");
    
    document.getElementById("status-message").textContent = data.state === "stopped" ? (data.message || "Stopped") : "Monitoring Active";
    document.getElementById("fps-readout").textContent    = `${data.fps} fps`;
    document.getElementById("feed-fps").textContent        = `${data.fps} fps`;

    document.getElementById("detail-state").textContent   = data.state === "stopped" ? "Stopped" : "Monitoring ✓";
    document.getElementById("detail-today").textContent   = data.today_count ?? "0";
    document.getElementById("detail-uptime").textContent  = formatUptime(data.uptime ?? 0);

    document.getElementById("kv-engine").textContent  = data.state === "stopped" ? "Stopped" : "Active";
    document.getElementById("kv-fps").textContent     = `${data.fps} fps`;
    document.getElementById("kv-today").textContent   = data.today_count ?? "0";

    const currentTodayCount = data.today_count ?? 0;
    if (currentTodayCount > lastIncidentCount && lastIncidentCount !== 0) {
      toast("Accident detected! Alert automatically dispatched.", "warning", 6000);
    }
    lastIncidentCount = currentTodayCount;

  } catch {
    document.getElementById("status-message").textContent = "Backend unreachable";
    document.getElementById("status-dot").className = "status-dot stopped";
  }
}

function formatUptime(secs) {
  if (!secs) return "—";
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60), s = Math.floor(secs % 60);
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

setInterval(pollStatus, 2500);
pollStatus();

// ================================================================ INCIDENTS

function fmtConf(c) { return `${Math.round(c * 100)}%`; }
function fmtTs(iso) {
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}
function gpsLink(lat, lon) {
  if (lat == null || lon == null) return null;
  return `https://www.google.com/maps?q=${lat},${lon}`;
}

// -------------- History ---------------
let historyData   = [];

async function loadHistory() {
  try {
    const res = await fetch("/api/incidents/history");
    historyData = await res.json();
    renderHistory();
  } catch {
    toast("Failed to load history", "error");
  }
}

function renderHistory() {
  const tbody    = document.getElementById("history-body");
  const emptyMsg = document.getElementById("history-empty");

  if (historyData.length === 0) {
    tbody.innerHTML = "";
    emptyMsg.hidden = false;
    return;
  }
  emptyMsg.hidden = true;

  tbody.innerHTML = historyData.map(inc => {
    let alertCell = inc.alert_sent === 1
        ? `<span class="alert-sent-ok">Sent ✓</span>`
        : `<span class="alert-sent-fail">Failed${inc.alert_error ? ": " + inc.alert_error : ""}</span>`;

    const link = gpsLink(inc.gps_lat, inc.gps_lon);
    const gpsCell = link ? `<a href="${link}" target="_blank" rel="noopener" title="View on Maps">📍</a>` : "—";
    
    return `
    <tr>
      <td><img src="/snapshots/${inc.snapshot_path}" alt="Snapshot" loading="lazy"></td>
      <td>${fmtTs(inc.created_at)}</td>
      <td>${inc.camera_id}</td>
      <td><span class="confidence-pill" style="font-size: 11px; padding: 2px 8px; border-radius: 10px; background: var(--amber-subtle); border: 1px solid var(--amber-dim); color: var(--amber);">${fmtConf(inc.confidence)}</span></td>
      <td>${gpsCell}</td>
      <td>${alertCell}</td>
    </tr>`;
  }).join("");
}

// ================================================================ VIDEO FEED RECONNECT
function reconnectFeed() {
  const img = document.getElementById("video-feed");
  if (!img) return;
  img.src = "/video_feed?t=" + Date.now();
}

(function setupFeedResilience() {
  const img = document.getElementById("video-feed");
  if (!img) return;
  img.addEventListener("error", () => {
    setTimeout(reconnectFeed, 2000);
  });
  setInterval(() => {
    if (!img.complete || img.naturalWidth === 0) {
      reconnectFeed();
    }
  }, 30000);
})();

// ================================================================ SETTINGS
const state = { contacts: [] };

// ---- Source type selector ----
const sourceLabels = {
  webcam: "Webcam index (e.g. 0)",
  file:   "File path (e.g. C:\\videos\\clip.mp4)",
  rtsp:   "RTSP URL (e.g. rtsp://192.168.1.1/stream)",
  http:   "HTTP/HLS URL (e.g. http://...)",
};
document.querySelectorAll("input[name='src-type']").forEach(radio => {
  radio.addEventListener("change", () => {
    const span = document.getElementById("source-label-text");
    if (span) span.textContent = sourceLabels[radio.value];
    const inp = document.getElementById("s-video-source");
    if (radio.value === "webcam") inp.placeholder = "0";
    else if (radio.value === "rtsp") inp.placeholder = "rtsp://192.168.1.1:554/stream1";
    else if (radio.value === "http") inp.placeholder = "http://camera.local/stream";
    else inp.placeholder = "C:\\videos\\test.mp4";
  });
});

function detectSourceType(source) {
  if (source === null || source === "" || /^-?\d+$/.test(source.trim())) return "webcam";
  const s = source.trim().toLowerCase();
  if (s.startsWith("rtsp://")) return "rtsp";
  if (s.startsWith("http://") || s.startsWith("https://")) return "http";
  return "file";
}

// ---- GPS preview ----
function updateGpsPreview() {
  const lat  = parseFloat(document.getElementById("s-gps-lat").value);
  const lon  = parseFloat(document.getElementById("s-gps-lon").value);
  const prev = document.getElementById("gps-preview");
  const link = document.getElementById("gps-preview-link");
  if (!isNaN(lat) && !isNaN(lon)) {
    prev.hidden = false;
    link.href   = `https://www.google.com/maps?q=${lat},${lon}`;
  } else {
    prev.hidden = true;
  }
}
document.getElementById("s-gps-lat").addEventListener("input", updateGpsPreview);
document.getElementById("s-gps-lon").addEventListener("input", updateGpsPreview);

// ---- Sliders ----
document.getElementById("s-confidence").addEventListener("input", e => {
  document.getElementById("conf-readout").textContent = parseFloat(e.target.value).toFixed(2);
});
document.getElementById("s-min-box-area").addEventListener("input", e => {
  document.getElementById("box-area-readout").textContent = `${Math.round(parseFloat(e.target.value) * 100)}%`;
});

// ---- Contacts rendering ----
function renderContacts() {
  const container = document.getElementById("contacts-list");
  if (state.contacts.length === 0) {
    container.innerHTML =
      `<p class="field-note" style="margin-bottom:14px;">No emergency email contacts configured.</p>`;
    return;
  }
  container.innerHTML = state.contacts.map((c, i) => {
    return `
    <div class="contact-card">
      <div class="contact-card-header">
        <span class="contact-name-label">${c.name || "Contact " + (i + 1)}</span>
        <button type="button" class="btn-danger" onclick="removeContact(${i})">✕ Remove</button>
      </div>
      <div class="contact-fields-grid">
        <label class="field-label">Name
          <input type="text" class="field-input" placeholder="Hospital / Police"
            value="${esc(c.name || '')}" oninput="updateContact(${i},'name',this.value)">
        </label>
        <label class="field-label">Email address
          <input type="email" class="field-input" placeholder="john@example.com"
            value="${esc(c.email || '')}" oninput="updateContact(${i},'email',this.value)">
        </label>
      </div>
    </div>`;
  }).join("");
}

function esc(s) {
  return String(s).replace(/&/g,"&amp;").replace(/"/g,"&quot;").replace(/</g,"&lt;");
}

function updateContact(i, field, value) { state.contacts[i][field] = value; renderContacts(); }
function removeContact(i) { state.contacts.splice(i, 1); renderContacts(); }
window.updateContact = updateContact;
window.removeContact = removeContact;

document.getElementById("add-contact-btn").addEventListener("click", () => {
  state.contacts.push({ name: "", email: "" });
  renderContacts();
});

// ---- Load settings ----
async function loadSettings() {
  try {
    const res = await fetch("/api/settings");
    const s   = await res.json();

    document.getElementById("s-camera-id").value      = s.camera_id ?? "";
    document.getElementById("s-video-source").value   = s.video_source ?? "0";
    document.getElementById("s-model-path").value     = s.model_path ?? "";
    document.getElementById("s-confidence").value     = s.confidence_threshold ?? 0.5;
    document.getElementById("conf-readout").textContent = parseFloat(s.confidence_threshold ?? 0.5).toFixed(2);
    document.getElementById("s-cooldown").value       = s.cooldown_seconds ?? 15;
    document.getElementById("s-min-box-area").value   = s.min_box_area_ratio ?? 0.02;
    document.getElementById("box-area-readout").textContent = `${Math.round((s.min_box_area_ratio ?? 0.02) * 100)}%`;
    document.getElementById("s-frames-required").value = s.consecutive_frames_required ?? 5;

    // GPS
    const gps = s.gps_location || {};
    document.getElementById("s-gps-lat").value = gps.lat ?? "";
    document.getElementById("s-gps-lon").value = gps.lon ?? "";
    updateGpsPreview();

    // SMTP
    document.getElementById("s-smtp-host").value     = s.smtp_host ?? "smtp.gmail.com";
    document.getElementById("s-smtp-port").value     = s.smtp_port ?? 587;
    document.getElementById("s-smtp-user").value     = s.smtp_user ?? "";
    document.getElementById("s-smtp-password").value = "";  // never prefill password
    document.getElementById("s-smtp-from").value     = s.smtp_from ?? "";

    if (s.camera_id) {
      document.getElementById("camera-id-label").textContent = s.camera_id;
    }

    const srcType = detectSourceType(s.video_source);
    const radio = document.querySelector(`input[name='src-type'][value='${srcType}']`);
    if (radio) { radio.checked = true; radio.dispatchEvent(new Event("change")); }

    state.contacts = (s.emergency_contacts || []).map(c => ({
      name: c.name || "", email: c.email || ""
    }));
    renderContacts();
  } catch (e) {
    toast("Failed to load settings", "error");
  }
}

// ---- Save settings ----
document.getElementById("settings-form").addEventListener("submit", async e => {
  e.preventDefault();
  const saveBtn  = document.getElementById("save-btn");
  const spinner  = document.getElementById("save-spinner");
  saveBtn.disabled = true;
  spinner.hidden   = false;

  const latVal = document.getElementById("s-gps-lat").value.trim();
  const lonVal = document.getElementById("s-gps-lon").value.trim();

  const payload = {
    camera_id:                   document.getElementById("s-camera-id").value.trim(),
    video_source:                document.getElementById("s-video-source").value.trim(),
    model_path:                  document.getElementById("s-model-path").value.trim(),
    confidence_threshold:        parseFloat(document.getElementById("s-confidence").value),
    cooldown_seconds:            parseFloat(document.getElementById("s-cooldown").value),
    min_box_area_ratio:          parseFloat(document.getElementById("s-min-box-area").value),
    consecutive_frames_required: parseInt(document.getElementById("s-frames-required").value, 10),
    gps_location: {
      lat: latVal !== "" ? parseFloat(latVal) : null,
      lon: lonVal !== "" ? parseFloat(lonVal) : null,
    },
    smtp_host:     document.getElementById("s-smtp-host").value.trim(),
    smtp_port:     parseInt(document.getElementById("s-smtp-port").value, 10),
    smtp_user:     document.getElementById("s-smtp-user").value.trim(),
    smtp_password: document.getElementById("s-smtp-password").value,
    smtp_from:     document.getElementById("s-smtp-from").value.trim(),
    emergency_contacts: state.contacts.filter(c => c.name || c.email),
  };

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      toast("Settings saved — detection restarting in background…", "success");
      if (payload.camera_id) {
        document.getElementById("camera-id-label").textContent = payload.camera_id;
      }
      const overlay = document.getElementById("feed-overlay-msg");
      overlay.hidden = false;
      setTimeout(() => {
        overlay.hidden = true;
        reconnectFeed();
      }, 2500);
    } else {
      const err = await res.json();
      toast(`Failed to save: ${err.detail || "unknown error"}`, "error");
    }
  } catch {
    toast("Network error while saving settings", "error");
  } finally {
    saveBtn.disabled = false;
    spinner.hidden   = true;
  }
});

// ---- Test alert ----
document.getElementById("test-alert-btn").addEventListener("click", async () => {
  const btn = document.getElementById("test-alert-btn");
  btn.disabled = true;
  btn.textContent = "Sending…";
  try {
    const res  = await fetch("/api/test-alert", { method: "POST" });
    const data = await res.json();
    if (!res.ok) {
      toast(`Test alert failed: ${data.detail || "unknown"}`, "error");
    } else if (data.success) {
      toast("Test alert sent successfully ✓", "success");
    } else {
      toast(`Test alert partially failed: ${data.error ?? "check contacts/SMTP settings"}`, "warning", 7000);
    }
  } catch {
    toast("Network error while sending test alert", "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "⚡ Send Test Alert";
  }
});