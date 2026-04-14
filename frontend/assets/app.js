const state = {
  summary: {
    mode: "-",
    track_count: 0,
    ammo: { sam: 0, ciws_rounds: 0 },
    sensors: { acoustic: "-", irst: "-", radar: "-" },
    effector: "-",
    radar_emitting: false,
  },
  tracks: [],
  defendedZones: [],
  samBatteries: [],
  events: [],
  battleLog: [],
  ciws: {},
  passive_tracking: {},
  defense_config: {},
  scenario: {
    name: "-",
    status: "RUNNING",
    execution_state: "RUNNING",
    doctrine_mode: "BALANCED",
    elapsed_s: 0,
    available_scenarios: [],
    available_doctrine_modes: [],
  },
  report: {},
  filters: new Set(["ALL"]),
  selectedTrackId: null,
  mapCursor: { x: 0, y: 0, active: false },
  mapSelection: null,
  showBatteryCoverage: false,
  showConfidenceRings: false,
  tacticalScale: "AUTO",
  battleLogCategoryFilter: "ALL",
  battleLogTrackFilter: "ALL",
  eoirMode: "EO",
  weaponActivity: {
    missile: { activeUntil: 0, lastMessage: "No launch", lastTimestamp: null },
    ciws: { activeUntil: 0, lastMessage: "No fire", lastTimestamp: null },
  },
};

const elements = {
  mode: document.getElementById("mode-value"),
  trackCount: document.getElementById("track-count-value"),
  ammo: document.getElementById("ammo-value"),
  sensors: document.getElementById("sensor-value"),
  effector: document.getElementById("effector-value"),
  scenario: document.getElementById("scenario-value"),
  time: document.getElementById("time-value"),
  connection: document.getElementById("connection-status"),
  radar: document.getElementById("radar-pill"),
  stopButton: document.getElementById("stop-button"),
  pauseButton: document.getElementById("pause-button"),
  stepButton: document.getElementById("step-button"),
  resetButton: document.getElementById("reset-button"),
  reloadButton: document.getElementById("reload-button"),
  battleLogExportButton: document.getElementById("battle-log-export-button"),
  reportExportButton: document.getElementById("report-export-button"),
  scenarioSelect: document.getElementById("scenario-select"),
  doctrineSelect: document.getElementById("doctrine-select"),
  eoirModeSelect: document.getElementById("eoir-mode-select"),
  battleLogCategoryFilter: document.getElementById("battle-log-category-filter"),
  battleLogTrackFilter: document.getElementById("battle-log-track-filter"),
  mapCursorValue: document.getElementById("map-cursor-value"),
  mapSelectedValue: document.getElementById("map-selected-value"),
  zoomSelect: document.getElementById("zoom-select"),
  coverageToggleButton: document.getElementById("coverage-toggle-button"),
  confidenceToggleButton: document.getElementById("confidence-toggle-button"),
  copyCoordinatesButton: document.getElementById("copy-coordinates-button"),
  eoirTargetPill: document.getElementById("eoir-target-pill"),
  radarProfilePill: document.getElementById("radar-profile-pill"),
  missileFeedStatus: document.getElementById("missile-feed-status"),
  ciwsFeedStatus: document.getElementById("ciws-feed-status"),
  weaponsActivity: document.getElementById("weapons-activity"),
  trackTable: document.getElementById("track-table-body"),
  eventLog: document.getElementById("event-log"),
  battleLog: document.getElementById("battle-log"),
  defenseConfig: document.getElementById("defense-config-status"),
  ciws: document.getElementById("ciws-status"),
  passive: document.getElementById("passive-status"),
  sam: document.getElementById("sam-status"),
  zones: document.getElementById("zone-status"),
  detail: document.getElementById("track-detail"),
  report: document.getElementById("report-panel"),
  eoirCanvas: document.getElementById("eoir-canvas"),
  canvas: document.getElementById("tactical-canvas"),
  radarProfileCanvas: document.getElementById("radar-profile-canvas"),
  missileFeedCanvas: document.getElementById("missile-feed-canvas"),
  ciwsFeedCanvas: document.getElementById("ciws-feed-canvas"),
  filters: document.getElementById("filter-bar"),
};

const filterOptions = ["ALL", "JET", "DRONE", "HELICOPTER", "CRUISE_MISSILE", "BALLISTIC_MISSILE", "MISSILE"];
const EXPECTED_SCHEMA_VERSION = "0.2.0";
const TACTICAL_MAX_RANGE_M = 10000;

class TacticalRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  }

  draw(tracks, zones = [], batteries = [], showBatteryCoverage = false, showConfidenceRings = false, maxRange = TACTICAL_MAX_RANGE_M, selectedTrackId = null) {
    const { ctx, canvas } = this;
    const w = canvas.width;
    const h = canvas.height;
    const centerX = w / 2;
    const centerY = h / 2;
    const now = performance.now();
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "rgba(126, 209, 245, 0.25)";
    ctx.lineWidth = 1;
    [0.2, 0.4, 0.6, 0.8].forEach((factor) => {
      ctx.beginPath();
      ctx.arc(centerX, centerY, factor * (w * 0.44), 0, Math.PI * 2);
      ctx.stroke();
    });
    ctx.beginPath();
    ctx.moveTo(centerX, 16);
    ctx.lineTo(centerX, h - 16);
    ctx.moveTo(16, centerY);
    ctx.lineTo(w - 16, centerY);
    ctx.stroke();

    ctx.fillStyle = "#dbe7e2";
    ctx.beginPath();
    ctx.arc(centerX, centerY, 7, 0, Math.PI * 2);
    ctx.fill();

    zones.forEach((zone) => {
      const x = centerX + (zone.position.x / maxRange) * (w * 0.44);
      const y = centerY - (zone.position.y / maxRange) * (h * 0.44);
      const radius = Math.max(10, (zone.radius_m / maxRange) * (w * 0.44));
      const zoneColor =
        zone.status === "LOST" ? "rgba(255, 127, 107, 0.75)" : zone.status === "DAMAGED" ? "rgba(255, 179, 71, 0.7)" : "rgba(108, 201, 161, 0.6)";
      ctx.strokeStyle = zoneColor;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.stroke();
      ctx.fillStyle = "#dbe7e2";
      ctx.font = "12px IBM Plex Mono, monospace";
      ctx.fillText(`${zone.name} ${zone.health}%`, x - radius, y - radius - 6);
    });

    batteries.forEach((battery) => {
      const x = centerX + (battery.position.x / maxRange) * (w * 0.44);
      const y = centerY - (battery.position.y / maxRange) * (h * 0.44);
      const ready = (battery.status || "READY") === "READY";
      if (showBatteryCoverage) {
        const coverageRadius = Math.max(8, (safeNumber(battery.max_range_m, 0) / maxRange) * (w * 0.44));
        ctx.strokeStyle = ready ? "rgba(133, 255, 246, 0.82)" : "rgba(220, 255, 120, 0.78)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, coverageRadius, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.strokeStyle = ready ? "rgba(126, 209, 245, 0.95)" : "rgba(255, 179, 71, 0.9)";
      ctx.fillStyle = ready ? "rgba(126, 209, 245, 0.25)" : "rgba(255, 179, 71, 0.24)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.rect(x - 9, y - 9, 18, 18);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#dbe7e2";
      ctx.font = "12px IBM Plex Mono, monospace";
      ctx.fillText(`${battery.id} ${battery.ammo_remaining}`, x + 14, y + 4);
    });

    tracks.forEach((track) => {
      const x = centerX + (track.position.x / maxRange) * (w * 0.44);
      const y = centerY - (track.position.y / maxRange) * (h * 0.44);
      const color = iffColor(track.iff);
      const selected = track.id === selectedTrackId;
      const confidence = Math.max(0, Math.min(99, track.track_confidence ?? 0));

      if (showConfidenceRings && confidence < 99) {
        const uncertaintyM = 120 + ((100 - confidence) * 18);
        const uncertaintyRadius = Math.max(8, (uncertaintyM / maxRange) * (w * 0.44));
        ctx.strokeStyle = selected ? "rgba(248, 241, 180, 0.85)" : "rgba(239, 215, 139, 0.65)";
        ctx.lineWidth = 1.5;
        ctx.setLineDash([5, 5]);
        ctx.beginPath();
        ctx.arc(x, y, uncertaintyRadius, 0, Math.PI * 2);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (selected) {
        const pulse = 12 + (((now / 220) % 1) * 8);
        ctx.strokeStyle = "rgba(248, 241, 180, 0.85)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, pulse, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = selected ? 3 : 2;

      ctx.beginPath();
      ctx.arc(x, y, selected ? 8 : 6, 0, Math.PI * 2);
      ctx.fill();

      const heading = ((track.heading_deg || 0) * Math.PI) / 180;
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(x + Math.cos(heading) * (selected ? 22 : 16), y - Math.sin(heading) * (selected ? 22 : 16));
      ctx.stroke();

      ctx.font = "12px IBM Plex Mono, monospace";
      ctx.fillText(
        selected ? `${track.id} ${track.track_confidence ?? 0}%` : track.id,
        x + 10,
        y - 10,
      );
    });
  }
}

const renderer = new TacticalRenderer(elements.canvas);

function currentTacticalRange() {
  if (state.tacticalScale !== "AUTO") {
    return Number(state.tacticalScale);
  }
  const selectedTrack = state.tracks.find((track) => track.id === state.selectedTrackId);
  if (selectedTrack && selectedTrack.range_m <= 600) {
    return 500;
  }
  if (selectedTrack && selectedTrack.range_m <= 2500) {
    return 2000;
  }
  return TACTICAL_MAX_RANGE_M;
}

function canvasPointToWorld(canvas, clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;
  const px = (clientX - rect.left) * scaleX;
  const py = (clientY - rect.top) * scaleY;
  const centerX = canvas.width / 2;
  const centerY = canvas.height / 2;
  const usableRadiusX = canvas.width * 0.44;
  const usableRadiusY = canvas.height * 0.44;
  const activeRange = currentTacticalRange();
  return {
    x: Math.round(((px - centerX) / usableRadiusX) * activeRange),
    y: Math.round(((centerY - py) / usableRadiusY) * activeRange),
  };
}

class EOIRRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  }

  draw(track, mode = "EO", scenarioRunning = true) {
    const { ctx, canvas } = this;
    const w = canvas.width;
    const h = canvas.height;
    const now = performance.now();
    ctx.clearRect(0, 0, w, h);

    const bg = ctx.createLinearGradient(0, 0, 0, h);
    if (mode === "IR_WHITE") {
      bg.addColorStop(0, "#e9edef");
      bg.addColorStop(0.45, "#8f9ea6");
      bg.addColorStop(1, "#0d1519");
    } else if (mode === "IR_BLACK") {
      bg.addColorStop(0, "#212b30");
      bg.addColorStop(0.45, "#55646d");
      bg.addColorStop(1, "#f4f2e6");
    } else {
      bg.addColorStop(0, "#536570");
      bg.addColorStop(0.45, "#203039");
      bg.addColorStop(1, "#05090b");
    }
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    if (mode === "EO") {
      const grain = 0.03 + (((now / 180) % 1) * 0.015);
      ctx.fillStyle = `rgba(255,255,255,${grain})`;
      for (let i = 0; i < 80; i += 1) {
        ctx.fillRect((i * 29) % w, ((i * 41) + now * 0.02) % h, 1, 1);
      }
    } else {
      ctx.fillStyle = mode === "IR_BLACK" ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.08)";
      for (let i = 0; i < 70; i += 1) {
        ctx.fillRect((i * 31) % w, ((i * 47) + now * 0.015) % h, 2, 1);
      }
    }

    ctx.fillStyle = mode === "IR_BLACK" ? "rgba(240, 236, 224, 0.9)" : "rgba(9, 14, 16, 0.95)";
    ctx.fillRect(0, h * 0.78, w, h * 0.22);

    const hudColor = mode === "EO" ? "rgba(126, 209, 245, 0.85)" : mode === "IR_WHITE" ? "rgba(22, 28, 31, 0.9)" : "rgba(241, 240, 232, 0.92)";
    ctx.strokeStyle = hudColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(w * 0.5, h * 0.15);
    ctx.lineTo(w * 0.5, h * 0.85);
    ctx.moveTo(w * 0.12, h * 0.5);
    ctx.lineTo(w * 0.88, h * 0.5);
    ctx.stroke();

    if (!track) {
      ctx.fillStyle = mode === "IR_BLACK" ? "#111518" : "#dbe7e2";
      ctx.font = '18px "IBM Plex Mono", monospace';
      ctx.fillText("NO TARGET SELECTED", w * 0.28, h * 0.52);
      return;
    }

    const scale = Math.max(0.42, 1.18 - track.range_m / 8500);
    const driftX = Math.sin((now / 300) + track.range_m / 600) * Math.max(2, track.range_m / 1500);
    const driftY = Math.cos((now / 360) + track.speed_mps / 70) * Math.max(2, track.range_m / 2200);
    const centerX = (w * 0.5) + driftX;
    const centerY = (h * 0.46) + driftY;
    const lockConfidence = Math.max(0, Math.min(99, Math.round(track.track_confidence ?? 0)));
    const designation = track.fusion_state === "FIRE" || track.engagement_state === "ENGAGING" ? "LASER / HARD LOCK" : "TRACK / SOFT LOCK";
    const silhouetteColor = mode === "IR_BLACK" ? "#111518" : mode === "IR_WHITE" ? "#f2f0e6" : "rgba(255, 245, 196, 0.9)";

    ctx.strokeStyle = hudColor;
    ctx.strokeRect(centerX - 86, centerY - 64, 172, 128);
    ctx.beginPath();
    ctx.moveTo(centerX - 86, centerY - 64);
    ctx.lineTo(centerX - 62, centerY - 64);
    ctx.moveTo(centerX + 62, centerY - 64);
    ctx.lineTo(centerX + 86, centerY - 64);
    ctx.moveTo(centerX - 86, centerY + 64);
    ctx.lineTo(centerX - 62, centerY + 64);
    ctx.moveTo(centerX + 62, centerY + 64);
    ctx.lineTo(centerX + 86, centerY + 64);
    ctx.stroke();

    ctx.save();
    ctx.translate(centerX, centerY);
    ctx.scale(scale, scale);
    ctx.strokeStyle = iffColor(track.iff);
    ctx.fillStyle = silhouetteColor;
    ctx.lineWidth = 3;
    this._drawSilhouette(track, ctx);
    ctx.restore();

    ctx.fillStyle = mode === "IR_BLACK" ? "#111518" : "#dbe7e2";
    ctx.font = '14px "IBM Plex Mono", monospace';
    ctx.fillText(`TARGET ${track.id}`, 18, 24);
    ctx.fillText(`MODE ${mode.replace("_", " ")}`, w - 176, 24);
    ctx.fillText(`TYPE ${track.type}`, 18, h - 60);
    ctx.fillText(`RANGE ${Math.round(track.range_m)} M`, 18, h - 40);
    ctx.fillText(`SPD ${Math.round(track.speed_mps)} M/S`, 18, h - 20);
    ctx.fillText(`ALT ${Math.round(track.altitude_m || estimatedAltitude(track))} M`, w - 180, h - 60);
    ctx.fillText(`LOCK ${lockConfidence}%`, w - 170, h - 40);
    ctx.fillText(`STATE ${track.fusion_state}`, w - 176, h - 20);

    ctx.font = '12px "IBM Plex Mono", monospace';
    ctx.fillText(`STATUS ${track.target_status}`, 18, 46);
    ctx.fillText(`DESIGNATION ${designation}`, 18, 64);
    if (!scenarioRunning) {
      ctx.fillText("FEED HOLD / SCENARIO COMPLETE", w - 220, 46);
    }
  }

  _drawSilhouette(track, ctx) {
    const type = track.type || "UNKNOWN";
    if (type === "JET") {
      ctx.beginPath();
      ctx.moveTo(0, -42);
      ctx.lineTo(10, -8);
      ctx.lineTo(34, 2);
      ctx.lineTo(12, 8);
      ctx.lineTo(8, 36);
      ctx.lineTo(0, 24);
      ctx.lineTo(-8, 36);
      ctx.lineTo(-12, 8);
      ctx.lineTo(-34, 2);
      ctx.lineTo(-10, -8);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      return;
    }
    if (type === "HELICOPTER") {
      ctx.fillRect(-18, -8, 36, 18);
      ctx.strokeRect(-18, -8, 36, 18);
      ctx.beginPath();
      ctx.moveTo(-30, -18);
      ctx.lineTo(30, -18);
      ctx.moveTo(0, -18);
      ctx.lineTo(0, -30);
      ctx.moveTo(18, 10);
      ctx.lineTo(34, 10);
      ctx.stroke();
      return;
    }
    if (type === "DRONE") {
      ctx.beginPath();
      ctx.moveTo(0, -20);
      ctx.lineTo(10, -2);
      ctx.lineTo(24, 2);
      ctx.lineTo(8, 6);
      ctx.lineTo(0, 18);
      ctx.lineTo(-8, 6);
      ctx.lineTo(-24, 2);
      ctx.lineTo(-10, -2);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      return;
    }
    if (type === "CRUISE_MISSILE") {
      ctx.fillRect(-28, -5, 56, 10);
      ctx.strokeRect(-28, -5, 56, 10);
      ctx.beginPath();
      ctx.moveTo(28, -5);
      ctx.lineTo(38, 0);
      ctx.lineTo(28, 5);
      ctx.moveTo(-8, -12);
      ctx.lineTo(6, 0);
      ctx.lineTo(-8, 12);
      ctx.stroke();
      return;
    }
    if (type === "BALLISTIC_MISSILE") {
      ctx.beginPath();
      ctx.moveTo(0, -34);
      ctx.lineTo(12, -6);
      ctx.lineTo(12, 28);
      ctx.lineTo(-12, 28);
      ctx.lineTo(-12, -6);
      ctx.closePath();
      ctx.fill();
      ctx.stroke();
      return;
    }
    ctx.beginPath();
    ctx.arc(0, 0, 24, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
  }
}

class RadarProfileRenderer {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
  }

  draw(tracks, selectedTrack, zones = []) {
    const { ctx, canvas } = this;
    const w = canvas.width;
    const h = canvas.height;
    ctx.clearRect(0, 0, w, h);

    ctx.fillStyle = "#07141a";
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(126, 209, 245, 0.18)";
    ctx.lineWidth = 1;
    for (let i = 1; i <= 4; i += 1) {
      const y = 20 + ((h - 50) * i) / 5;
      ctx.beginPath();
      ctx.moveTo(44, y);
      ctx.lineTo(w - 18, y);
      ctx.stroke();
    }
    for (let i = 0; i <= 5; i += 1) {
      const x = 44 + ((w - 70) * i) / 5;
      ctx.beginPath();
      ctx.moveTo(x, 20);
      ctx.lineTo(x, h - 28);
      ctx.stroke();
    }

    ctx.strokeStyle = "rgba(126, 209, 245, 0.8)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(44, h - 28);
    ctx.lineTo(44, 20);
    ctx.lineTo(w - 18, 20);
    ctx.stroke();

    const maxRange = 10000;
    const maxAlt = 16000;
    tracks.forEach((track) => {
      const x = 44 + Math.min(track.range_m, maxRange) / maxRange * (w - 70);
      const altitude = estimatedAltitude(track);
      const y = (h - 28) - (Math.min(altitude, maxAlt) / maxAlt) * (h - 48);
      ctx.fillStyle = track.id === selectedTrack?.id ? "#f8f1b4" : iffColor(track.iff);
      ctx.beginPath();
      ctx.arc(x, y, track.id === selectedTrack?.id ? 6 : 4, 0, Math.PI * 2);
      ctx.fill();
      if (track.id === selectedTrack?.id) {
        ctx.strokeStyle = "rgba(248, 241, 180, 0.9)";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 11, 0, Math.PI * 2);
        ctx.stroke();
        ctx.fillStyle = "#f8f1b4";
        ctx.font = '11px "IBM Plex Mono", monospace';
        ctx.fillText(`${track.id} ${track.track_confidence ?? 0}%`, Math.min(x + 12, w - 130), Math.max(y - 10, 24));
      }
    });

    if (selectedTrack) {
      const arcStartX = 44;
      const arcEndX = 44 + Math.min(selectedTrack.range_m, maxRange) / maxRange * (w - 70);
      const arcPeakY = 34;
      ctx.strokeStyle = "rgba(255, 179, 71, 0.8)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(arcStartX, h - 28);
      ctx.quadraticCurveTo((arcStartX + arcEndX) / 2, arcPeakY, arcEndX, h - 28 - (estimatedAltitude(selectedTrack) / maxAlt) * (h - 48));
      ctx.stroke();
    }

    zones.forEach((zone) => {
      const zoneDistance = Math.sqrt((zone.position.x || 0) ** 2 + (zone.position.y || 0) ** 2);
      const x = 44 + Math.min(zoneDistance, maxRange) / maxRange * (w - 70);
      ctx.strokeStyle =
        zone.status === "LOST" ? "rgba(255, 127, 107, 0.85)" : zone.status === "DAMAGED" ? "rgba(255, 179, 71, 0.85)" : "rgba(108, 201, 161, 0.75)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, h - 34);
      ctx.lineTo(x, h - 18);
      ctx.stroke();
      ctx.fillStyle = "#dbe7e2";
      ctx.font = '11px "IBM Plex Mono", monospace';
      ctx.fillText(zone.name, x - 18, h - 40);
    });

    ctx.fillStyle = "#dbe7e2";
    ctx.font = '13px "IBM Plex Mono", monospace';
    ctx.fillText("ALT", 10, 26);
    ctx.fillText("DIST", w - 58, h - 8);
    ctx.fillText("10000m", w - 90, h - 30);
  }
}

const eoirRenderer = new EOIRRenderer(elements.eoirCanvas);
const radarProfileRenderer = new RadarProfileRenderer(elements.radarProfileCanvas);

class WeaponFeedRenderer {
  constructor(canvas, mode) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.mode = mode;
    this.activeUntil = 0;
  }

  trigger(durationMs) {
    this.activeUntil = Math.max(this.activeUntil, performance.now() + durationMs);
  }

  isActive(now = performance.now()) {
    return now < this.activeUntil;
  }

  stop() {
    this.activeUntil = 0;
  }

  draw(now, options = {}) {
    const { ctx, canvas } = this;
    const w = canvas.width;
    const h = canvas.height;
    const active = options.active || this.isActive(now);
    const phase = (now % 4000) / 4000;

    ctx.clearRect(0, 0, w, h);
    const sky = ctx.createLinearGradient(0, 0, 0, h);
    sky.addColorStop(0, active ? "#556f80" : "#3d5664");
    sky.addColorStop(0.55, active ? "#182936" : "#12202b");
    sky.addColorStop(1, "#05080b");
    ctx.fillStyle = sky;
    ctx.fillRect(0, 0, w, h);

    ctx.fillStyle = "rgba(10, 16, 18, 0.95)";
    ctx.fillRect(0, h * 0.72, w, h * 0.28);

    if (this.mode === "missile") {
      this._drawMissileFeed(ctx, w, h, phase, active);
    } else {
      this._drawCiwsFeed(ctx, w, h, phase, active, options.targeting);
    }

    ctx.strokeStyle = "rgba(126, 209, 245, 0.35)";
    ctx.lineWidth = 1;
    ctx.strokeRect(6, 6, w - 12, h - 12);
  }

  _drawMissileFeed(ctx, w, h, phase, active) {
    ctx.fillStyle = "#26353d";
    ctx.fillRect(w * 0.1, h * 0.62, w * 0.2, h * 0.1);
    ctx.fillRect(w * 0.16, h * 0.54, w * 0.08, h * 0.08);

    if (active) {
      const trailX = w * (0.24 + phase * 0.56);
      const trailY = h * (0.58 - phase * 0.28);
      ctx.strokeStyle = "rgba(255, 187, 71, 0.85)";
      ctx.lineWidth = 5;
      ctx.beginPath();
      ctx.moveTo(w * 0.23, h * 0.58);
      ctx.lineTo(trailX, trailY);
      ctx.stroke();

      ctx.fillStyle = "#fbe0a7";
      ctx.beginPath();
      ctx.arc(trailX, trailY, 6, 0, Math.PI * 2);
      ctx.fill();

      ctx.fillStyle = "rgba(255, 149, 77, 0.45)";
      ctx.beginPath();
      ctx.arc(w * 0.22, h * 0.58, 18 + ((phase * 40) % 12), 0, Math.PI * 2);
      ctx.fill();
    } else {
      ctx.fillStyle = "rgba(126, 209, 245, 0.18)";
      ctx.fillRect(w * 0.22, h * 0.56, 18, 6);
    }
  }

  _drawCiwsFeed(ctx, w, h, phase, active, targeting) {
    ctx.fillStyle = "#31424a";
    ctx.fillRect(w * 0.08, h * 0.64, w * 0.18, h * 0.08);
    ctx.fillRect(w * 0.18, h * 0.48, w * 0.12, h * 0.06);

    if (active) {
      for (let i = 0; i < 8; i += 1) {
        const offset = ((phase * 1.8) + i * 0.11) % 1;
        const x = w * (0.28 + offset * 0.62);
        const y = h * (0.5 - offset * 0.08 + Math.sin((phase + i) * 12) * 0.012);
        ctx.fillStyle = i % 2 === 0 ? "#ffb347" : "#f8f1b4";
        ctx.fillRect(x, y, 8, 2);
      }

      ctx.fillStyle = "rgba(255, 180, 71, 0.6)";
      ctx.beginPath();
      ctx.arc(w * 0.29, h * 0.51, 16 + ((phase * 20) % 10), 0, Math.PI * 2);
      ctx.fill();
    }

    if (targeting) {
      ctx.strokeStyle = "rgba(126, 209, 245, 0.8)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(w * 0.78, h * 0.25);
      ctx.lineTo(w * 0.78, h * 0.42);
      ctx.moveTo(w * 0.7, h * 0.34);
      ctx.lineTo(w * 0.86, h * 0.34);
      ctx.stroke();
    }
  }
}

const missileFeedRenderer = new WeaponFeedRenderer(elements.missileFeedCanvas, "missile");
const ciwsFeedRenderer = new WeaponFeedRenderer(elements.ciwsFeedCanvas, "ciws");

function initFilters() {
  filterOptions.forEach((type) => {
    const button = document.createElement("button");
    button.className = `filter-pill${type === "ALL" ? " active" : ""}`;
    button.textContent = type;
    button.addEventListener("click", () => toggleFilter(type, button));
    elements.filters.appendChild(button);
  });
}

function toggleFilter(type, button) {
  if (type === "ALL") {
    state.filters = new Set(["ALL"]);
    document.querySelectorAll(".filter-pill").forEach((pill) => {
      pill.classList.toggle("active", pill.textContent === "ALL");
    });
    render();
    return;
  }

  state.filters.delete("ALL");
  if (state.filters.has(type)) {
    state.filters.delete(type);
  } else {
    state.filters.add(type);
  }

  if (state.filters.size === 0) {
    state.filters.add("ALL");
  }

  document.querySelectorAll(".filter-pill").forEach((pill) => {
    const pillType = pill.textContent;
    pill.classList.toggle("active", state.filters.has(pillType));
  });

  render();
}

function iffColor(iff) {
  if (iff === "FRIEND") return "#6cc9a1";
  if (iff === "HOSTILE") return "#ff7f6b";
  return "#efd78b";
}

function estimatedAltitude(track) {
  if (typeof track?.altitude_m === "number" && Number.isFinite(track.altitude_m)) {
    return track.altitude_m;
  }
  const base = {
    CRUISE_MISSILE: 250,
    BALLISTIC_MISSILE: 14000,
    MISSILE: 1800,
    JET: 5200,
    HELICOPTER: 1400,
    DRONE: 2200,
  }[track?.type] ?? 2500;
  const variance = ((track?.id || "").split("").reduce((sum, char) => sum + char.charCodeAt(0), 0) % 900) - 450;
  return Math.max(300, base + variance);
}

function visibleTracks() {
  if (state.filters.has("ALL")) {
    return state.tracks;
  }
  return state.tracks.filter((track) => state.filters.has(track.type));
}

function isObject(value) {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function safeString(value, fallback = "-") {
  return typeof value === "string" && value.length > 0 ? value : fallback;
}

function safeNumber(value, fallback = 0) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function safeBoolean(value, fallback = false) {
  return typeof value === "boolean" ? value : fallback;
}

function normalizeTrack(track) {
  if (!isObject(track) || typeof track.id !== "string") {
    return null;
  }

  const position = isObject(track.position) ? track.position : {};
  return {
    id: track.id,
    type: safeString(track.type),
    range_m: safeNumber(track.range_m),
    speed_mps: safeNumber(track.speed_mps),
    altitude_m: safeNumber(track.altitude_m, estimatedAltitude(track)),
    priority: safeNumber(track.priority, 0),
    threat_score: safeNumber(track.threat_score, safeNumber(track.priority, 0)),
    iff: safeString(track.iff, "UNKNOWN"),
    engagement_state: safeString(track.engagement_state),
    fusion_state: safeString(track.fusion_state, "SILENT"),
    assigned_effector: safeString(track.assigned_effector, "MONITOR"),
    assigned_battery: track.assigned_battery == null ? null : safeString(track.assigned_battery),
    preferred_effector: safeString(track.preferred_effector, "MONITOR"),
    shot_doctrine: safeString(track.shot_doctrine),
    shots_planned: safeNumber(track.shots_planned, 0),
    target_health: safeNumber(track.target_health, 0),
    target_max_health: safeNumber(track.target_max_health, safeNumber(track.target_health, 0)),
    track_confidence: safeNumber(track.track_confidence, 0),
    confidence_reasons: Array.isArray(track.confidence_reasons)
      ? track.confidence_reasons.filter((item) => typeof item === "string")
      : [],
    target_status: safeString(track.target_status, "UNKNOWN"),
    threat_reasons: Array.isArray(track.threat_reasons)
      ? track.threat_reasons.filter((item) => typeof item === "string")
      : [],
    heading_deg: safeNumber(track.heading_deg, 0),
    alive: safeBoolean(track.alive, true),
    position: {
      x: safeNumber(position.x, 0),
      y: safeNumber(position.y, 0),
    },
  };
}

function normalizeEvent(event) {
  if (!isObject(event)) {
    return null;
  }
  return {
    timestamp: safeString(event.timestamp, new Date().toISOString()),
    level: safeString(event.level, "info"),
    category: safeString(event.category, "system"),
    message: safeString(event.message, "Malformed event payload received."),
  };
}

function normalizeBattleLogEntry(entry) {
  if (!isObject(entry)) {
    return null;
  }
  return {
    id: safeNumber(entry.id, 0),
    timestamp: safeString(entry.timestamp, new Date().toISOString()),
    time_s: safeNumber(entry.time_s, 0),
    source: safeString(entry.source, "system"),
    level: safeString(entry.level, "info"),
    category: safeString(entry.category, "system"),
    target_id: entry.target_id == null ? null : safeString(entry.target_id),
    message: safeString(entry.message, "Malformed battle log entry received."),
  };
}

function normalizeSnapshotEnvelope(message) {
  if (!isObject(message)) {
    throw new Error("message is not an object");
  }
  if (message.type !== "snapshot") {
    throw new Error(`unsupported message type: ${message.type ?? "missing"}`);
  }
  if (message.payload_type !== "snapshot") {
    throw new Error(`unsupported payload type: ${message.payload_type ?? "missing"}`);
  }
  if (!isObject(message.payload)) {
    throw new Error("snapshot payload is missing");
  }

  const payload = message.payload;
  const summary = isObject(payload.summary) ? payload.summary : {};
  const ammo = isObject(summary.ammo) ? summary.ammo : {};
  const sensors = isObject(summary.sensors) ? summary.sensors : {};
  const ciws = isObject(payload.ciws) ? payload.ciws : {};
  const passive = isObject(payload.passive_tracking) ? payload.passive_tracking : {};
  const defenseConfig = isObject(payload.defense_config) ? payload.defense_config : {};
  const scenario = isObject(payload.scenario) ? payload.scenario : {};
  const report = isObject(payload.report) ? payload.report : {};
  const defendedZones = Array.isArray(payload.defended_zones) ? payload.defended_zones : [];
  const samBatteries = Array.isArray(payload.sam_batteries)
    ? payload.sam_batteries
    : Array.isArray(summary.sam_batteries)
      ? summary.sam_batteries
      : [];

  return {
    schemaVersion: safeString(message.schema_version, "unknown"),
    payload: {
      summary: {
        mode: safeString(summary.mode),
        track_count: safeNumber(summary.track_count, 0),
        ammo: {
          sam: safeNumber(ammo.sam, 0),
          ciws_rounds: safeNumber(ammo.ciws_rounds, 0),
        },
        sensors: {
          acoustic: safeString(sensors.acoustic),
          irst: safeString(sensors.irst),
          radar: safeString(sensors.radar),
        },
        effector: safeString(summary.effector),
        radar_emitting: safeBoolean(summary.radar_emitting, false),
      },
      tracks: Array.isArray(payload.tracks)
        ? payload.tracks.map(normalizeTrack).filter(Boolean)
        : [],
      defended_zones: defendedZones
        .filter((zone) => isObject(zone))
        .map((zone) => ({
          id: safeString(zone.id, "ZONE"),
          name: safeString(zone.name, "Zone"),
          type: safeString(zone.type, "ZONE"),
          radius_m: safeNumber(zone.radius_m, 0),
          priority: safeNumber(zone.priority, 0),
          health: safeNumber(zone.health, 100),
          status: safeString(zone.status, "SECURE"),
          position: {
            x: safeNumber(isObject(zone.position) ? zone.position.x : 0, 0),
            y: safeNumber(isObject(zone.position) ? zone.position.y : 0, 0),
          },
        })),
      sam_batteries: samBatteries
        .filter((battery) => isObject(battery))
        .map((battery) => ({
          id: safeString(battery.id, "BTRY"),
          name: safeString(battery.name, "Battery"),
          max_range_m: safeNumber(battery.max_range_m, 0),
          ammo_remaining: safeNumber(battery.ammo_remaining, safeNumber(battery.ammo, 0)),
          max_channels: safeNumber(battery.max_channels, 1),
          status: safeString(battery.status, "READY"),
          position: {
            x: safeNumber(isObject(battery.position) ? battery.position.x : 0, 0),
            y: safeNumber(isObject(battery.position) ? battery.position.y : 0, 0),
          },
        })),
      events: Array.isArray(payload.events)
        ? payload.events.map(normalizeEvent).filter(Boolean)
        : [],
      battle_log: Array.isArray(payload.battle_log)
        ? payload.battle_log.map(normalizeBattleLogEntry).filter(Boolean)
        : [],
      ciws: {
        state: safeString(ciws.state),
        ammo_remaining: safeNumber(ciws.ammo_remaining, 0),
        heat: safeNumber(ciws.heat, 0),
        spin_up: safeNumber(ciws.spin_up, 0),
        cooldown_remaining: safeNumber(ciws.cooldown_remaining, 0),
        active_target_id: ciws.active_target_id == null ? null : safeString(ciws.active_target_id),
      },
      passive_tracking: {
        acoustic_state: safeString(passive.acoustic_state),
        irst_state: safeString(passive.irst_state),
        radar_state: safeString(passive.radar_state),
        radar_blink_seconds: safeNumber(passive.radar_blink_seconds, 0),
        active_sensors: Array.isArray(passive.active_sensors)
          ? passive.active_sensors.filter((item) => typeof item === "string")
          : [],
      },
      defense_config: {
        active_sensors: Array.isArray(defenseConfig.active_sensors)
          ? defenseConfig.active_sensors.filter((item) => typeof item === "string")
          : [],
        missile_channels: safeNumber(defenseConfig.missile_channels, 0),
        jammer_channels: safeNumber(defenseConfig.jammer_channels, 0),
        ciws_channels: safeNumber(defenseConfig.ciws_channels, 0),
        high_priority_doctrine: safeString(defenseConfig.high_priority_doctrine),
        standard_doctrine: safeString(defenseConfig.standard_doctrine),
        hold_fire_below_score: safeNumber(defenseConfig.hold_fire_below_score, 0),
      },
      scenario: {
        name: safeString(scenario.name),
        status: safeString(scenario.status, "RUNNING"),
        execution_state: safeString(scenario.execution_state, "RUNNING"),
        doctrine_mode: safeString(scenario.doctrine_mode, "BALANCED"),
        reason: safeString(scenario.reason, ""),
        elapsed_s: safeNumber(scenario.elapsed_s, 0),
        time_limit_s: safeNumber(scenario.time_limit_s, 180),
        revision: safeNumber(scenario.revision, 0),
        step_budget: safeNumber(scenario.step_budget, 0),
        available_scenarios: Array.isArray(scenario.available_scenarios)
          ? scenario.available_scenarios.filter((item) => typeof item === "string")
          : [],
        available_doctrine_modes: Array.isArray(scenario.available_doctrine_modes)
          ? scenario.available_doctrine_modes.filter((item) => typeof item === "string")
          : [],
      },
      report: {
        title: safeString(report.title, ""),
        outcome: safeString(report.outcome, ""),
        outcome_label: safeString(report.outcome_label, ""),
        executive_summary: safeString(report.executive_summary, ""),
        findings: Array.isArray(report.findings) ? report.findings.filter((item) => typeof item === "string") : [],
        recommendations: Array.isArray(report.recommendations)
          ? report.recommendations.filter((item) => typeof item === "string")
          : [],
        metrics: isObject(report.metrics) ? report.metrics : {},
        hostile_history: Array.isArray(report.hostile_history)
          ? report.hostile_history
              .filter((item) => isObject(item))
              .map((item) => ({
                id: safeString(item.id, "UNKNOWN"),
                type: safeString(item.type, "UNKNOWN"),
                final_status: safeString(item.final_status, "UNKNOWN"),
                engagement_state: safeString(item.engagement_state, "-"),
                target_health: safeNumber(item.target_health, 0),
                target_max_health: safeNumber(item.target_max_health, safeNumber(item.target_health, 0)),
                retreating: safeBoolean(item.retreating, false),
              }))
          : [],
      },
    },
  };
}

function pushSystemEvent(level, message) {
  state.events = [
    {
      timestamp: new Date().toISOString(),
      level,
      category: "ui",
      message,
    },
    ...state.events,
  ].slice(0, 24);
}

function noteWeaponActivity(kind, message, timestamp, durationMs) {
  const entry = state.weaponActivity[kind];
  if (!entry) {
    return;
  }
  entry.activeUntil = Math.max(entry.activeUntil, performance.now() + durationMs);
  entry.lastMessage = message;
  entry.lastTimestamp = timestamp;
}

function applyMessage(message) {
  let normalized;
  try {
    normalized = normalizeSnapshotEnvelope(message);
  } catch (error) {
    pushSystemEvent("warning", `Dropped invalid WebSocket message: ${error.message}.`);
    render();
    return;
  }

  if (normalized.schemaVersion !== EXPECTED_SCHEMA_VERSION) {
    pushSystemEvent(
      "warning",
      `Schema version mismatch: expected ${EXPECTED_SCHEMA_VERSION}, received ${normalized.schemaVersion}.`,
    );
  }

  const { payload } = normalized;
  state.summary = payload.summary;
  state.tracks = payload.tracks;
  state.defendedZones = payload.defended_zones;
  state.samBatteries = payload.sam_batteries;
  state.events = [...payload.events, ...state.events].slice(0, 24);
  state.battleLog = payload.battle_log;
  state.ciws = payload.ciws;
  state.passive_tracking = payload.passive_tracking;
  state.defense_config = payload.defense_config;
  state.scenario = payload.scenario;
  state.report = payload.report;
  if (state.scenario.status === "RUNNING") {
    payload.events.forEach((event) => {
      const text = (event.message || "").toLowerCase();
      if (text.includes("missile launched") || text.includes("opening fire with btry-") || text.includes("opening fire with sam")) {
        missileFeedRenderer.trigger(4500);
        noteWeaponActivity("missile", event.message, event.timestamp, 3200);
      }
      if (text.includes("rounds on target") || text.includes("assigned to ciws") || text.includes("opening fire with ciws")) {
        ciwsFeedRenderer.trigger(2500);
        noteWeaponActivity("ciws", event.message, event.timestamp, 2200);
      }
    });
  } else {
    missileFeedRenderer.stop();
    ciwsFeedRenderer.stop();
    state.weaponActivity.missile.activeUntil = 0;
    state.weaponActivity.ciws.activeUntil = 0;
  }
  if (!state.selectedTrackId && state.tracks.length > 0) {
    state.selectedTrackId = state.tracks[0].id;
  }
  if (state.selectedTrackId && !state.tracks.some((track) => track.id === state.selectedTrackId)) {
    state.selectedTrackId = state.tracks[0]?.id ?? null;
  }
  render();
}

function renderSummary() {
  elements.mode.textContent = state.summary.mode;
  elements.trackCount.textContent = state.summary.track_count;
  elements.ammo.textContent = `SAM ${state.summary.ammo.sam} / CIWS ${state.summary.ammo.ciws_rounds}`;
  elements.sensors.textContent =
    `${state.summary.sensors.acoustic} / ${state.summary.sensors.irst} / ${state.summary.sensors.radar}`;
  elements.effector.textContent = state.summary.effector;
  elements.scenario.textContent =
    `${state.scenario.execution_state}${state.scenario.name !== "-" ? ` / ${state.scenario.name}` : ""}`;
  elements.time.textContent = `${Math.round(state.scenario.elapsed_s)} / ${Math.round(state.scenario.time_limit_s || 180)} s`;
  elements.radar.textContent = state.summary.radar_emitting ? "Radar Emitting" : "Radar Silent";
  elements.radar.classList.toggle("emitting", state.summary.radar_emitting);
  elements.stopButton.disabled = state.scenario.status !== "RUNNING";
  elements.pauseButton.disabled = state.scenario.status !== "RUNNING";
  elements.pauseButton.textContent = state.scenario.execution_state === "PAUSED" ? "Resume" : "Pause";
  elements.stepButton.disabled = !(state.scenario.status === "RUNNING" && state.scenario.execution_state === "PAUSED");
  elements.resetButton.disabled = false;
  elements.reloadButton.disabled = false;
  renderScenarioSelector();
  renderDoctrineSelector();
  renderWeaponFeedStatus();
}

function renderMapHelper() {
  elements.mapCursorValue.textContent = state.mapCursor.active
    ? `x ${state.mapCursor.x} / y ${state.mapCursor.y}`
    : "move over map";
  elements.mapSelectedValue.textContent = state.mapSelection
    ? `x ${state.mapSelection.x} / y ${state.mapSelection.y}`
    : "click map";
  elements.copyCoordinatesButton.disabled = !state.mapSelection;
  elements.coverageToggleButton.classList.toggle("active", state.showBatteryCoverage);
  elements.confidenceToggleButton.classList.toggle("active", state.showConfidenceRings);
  elements.zoomSelect.value = String(state.tacticalScale);
}

function renderWeaponFeedStatus() {
  const scenarioRunning = state.scenario.status === "RUNNING";
  const missileActive =
    scenarioRunning && (
      state.tracks.some(
      (track) =>
        track.assigned_effector === "SAM" &&
        ["ASSIGNED", "ENGAGING", "HIT", "KILL_ASSESS"].includes(track.target_status),
      ) || missileFeedRenderer.isActive()
    );
  const ciwsActive =
    scenarioRunning && (
      state.ciws.state === "FIRING" ||
      state.tracks.some(
        (track) => track.assigned_effector === "CIWS" && ["ASSIGNED", "ENGAGING", "HIT"].includes(track.target_status),
      ) ||
      ciwsFeedRenderer.isActive()
    );

  elements.missileFeedStatus.textContent = missileActive ? "Launch Active" : "Standby";
  elements.ciwsFeedStatus.textContent = ciwsActive ? "Gun Active" : "Standby";
}

function renderPaneLabels() {
  const selectedTrack = state.tracks.find((track) => track.id === state.selectedTrackId) || null;
  elements.eoirTargetPill.textContent = selectedTrack ? `Target: ${selectedTrack.id}` : "Target: None";
  elements.eoirModeSelect.value = state.eoirMode;
  elements.radarProfilePill.textContent = selectedTrack
    ? `Track: ${selectedTrack.id} / ${Math.round(selectedTrack.range_m)}m / ${Math.round(selectedTrack.altitude_m || estimatedAltitude(selectedTrack))}m alt`
    : "Track: None";
}

function renderScenarioSelector() {
  const options = [...new Set([...(state.scenario.available_scenarios || []), state.scenario.name].filter(Boolean).filter((name) => name !== "-"))];
  const current = state.scenario.name;
  if (options.length === 0) {
    elements.scenarioSelect.innerHTML = '<option value="">No scenarios</option>';
    elements.scenarioSelect.disabled = true;
    return;
  }

  const selectedValue = elements.scenarioSelect.value;
  elements.scenarioSelect.innerHTML = options
    .map(
      (name) =>
        `<option value="${name}" ${name === current ? "selected" : ""}>${name}</option>`,
    )
    .join("");
  elements.scenarioSelect.disabled = false;
  if (options.includes(selectedValue) && selectedValue !== current) {
    elements.scenarioSelect.value = selectedValue;
  }
}

function renderDoctrineSelector() {
  const options = [...new Set([...(state.scenario.available_doctrine_modes || []), state.scenario.doctrine_mode].filter(Boolean))];
  const current = state.scenario.doctrine_mode;
  if (options.length === 0) {
    elements.doctrineSelect.innerHTML = '<option value="">No doctrines</option>';
    elements.doctrineSelect.disabled = true;
    return;
  }

  const selectedValue = elements.doctrineSelect.value;
  elements.doctrineSelect.innerHTML = options
    .map(
      (name) =>
        `<option value="${name}" ${name === current ? "selected" : ""}>${name}</option>`,
    )
    .join("");
  elements.doctrineSelect.disabled = false;
  if (options.includes(selectedValue) && selectedValue !== current) {
    elements.doctrineSelect.value = selectedValue;
  }
}

function renderTrackTable() {
  const rows = visibleTracks()
    .sort((a, b) => (b.threat_score ?? b.priority ?? 0) - (a.threat_score ?? a.priority ?? 0))
    .map(
      (track) => `
        <tr class="${track.id === state.selectedTrackId ? "selected-row" : ""}" data-track-id="${track.id}">
          <td>${track.id}</td>
          <td>${track.type}</td>
          <td>${Math.round(track.range_m)} m</td>
          <td>${Math.round(track.speed_mps)} m/s</td>
          <td>${track.threat_score ?? track.priority ?? "-"}</td>
          <td class="iff-${track.iff.toLowerCase()}">${track.iff}</td>
          <td>${renderDamageIndicator(track)}</td>
          <td><span class="state-pill fusion-${(track.fusion_state || "silent").toLowerCase()}">${track.fusion_state || "-"}</span></td>
          <td><span class="state-pill effector-${(track.assigned_effector || "monitor").toLowerCase().replaceAll("_", "-")}">${renderEffectorLabel(track)}</span></td>
          <td><span class="state-pill status-${(track.target_status || "unknown").toLowerCase().replaceAll("_", "-")}">${track.target_status || "-"}</span></td>
          <td>${track.engagement_state}</td>
        </tr>
      `
    )
    .join("");
  elements.trackTable.innerHTML = rows;
  elements.trackTable.querySelectorAll("tr[data-track-id]").forEach((row) => {
    row.addEventListener("click", () => {
      state.selectedTrackId = row.dataset.trackId;
      render();
    });
  });
}

function renderEvents() {
  elements.eventLog.innerHTML = state.events
    .map(
      (event) => `
        <div class="event-item ${event.level}">
          <div class="event-meta">
            <span>${new Date(event.timestamp).toLocaleTimeString()}</span>
            <span>${event.category}</span>
          </div>
          <div>${event.message}</div>
        </div>
      `
    )
    .join("");
}

function renderBattleLogFilters() {
  const categories = ["ALL", ...new Set(state.battleLog.map((entry) => entry.category).filter(Boolean))];
  const targets = ["ALL", ...new Set(state.battleLog.map((entry) => entry.target_id).filter(Boolean))];

  elements.battleLogCategoryFilter.innerHTML = categories
    .map((category) => `<option value="${category}">${category === "ALL" ? "All Categories" : category}</option>`)
    .join("");
  elements.battleLogTrackFilter.innerHTML = targets
    .map((target) => `<option value="${target}">${target === "ALL" ? "All Tracks" : target}</option>`)
    .join("");

  elements.battleLogCategoryFilter.value = categories.includes(state.battleLogCategoryFilter)
    ? state.battleLogCategoryFilter
    : "ALL";
  elements.battleLogTrackFilter.value = targets.includes(state.battleLogTrackFilter)
    ? state.battleLogTrackFilter
    : "ALL";
  state.battleLogCategoryFilter = elements.battleLogCategoryFilter.value || "ALL";
  state.battleLogTrackFilter = elements.battleLogTrackFilter.value || "ALL";
}

function renderBattleLog() {
  renderBattleLogFilters();
  const rows = state.battleLog
    .filter((entry) => state.battleLogCategoryFilter === "ALL" || entry.category === state.battleLogCategoryFilter)
    .filter((entry) => state.battleLogTrackFilter === "ALL" || entry.target_id === state.battleLogTrackFilter)
    .slice(-80)
    .reverse()
    .map(
      (entry) => `
        <div class="battle-log-item ${entry.level}">
          <div class="event-meta">
            <span>T+${entry.time_s.toString().padStart(3, "0")}s</span>
            <span>${entry.source} / ${entry.category}${entry.target_id ? ` / ${entry.target_id}` : ""}</span>
          </div>
          <div>${entry.message}</div>
        </div>
      `,
    )
    .join("");
  elements.battleLog.innerHTML = rows || '<div class="detail-empty">No battle log entries yet.</div>';
}

function renderWeaponsActivity() {
  const now = performance.now();
  const rows = [
    ["missile", "MISSILE", state.weaponActivity.missile],
    ["ciws", "CIWS", state.weaponActivity.ciws],
  ]
    .map(([key, label, entry]) => {
      const active = now < entry.activeUntil && state.scenario.status === "RUNNING";
      const timeLabel = entry.lastTimestamp ? new Date(entry.lastTimestamp).toLocaleTimeString() : "--:--:--";
      return `
        <div class="weapon-activity-row">
          <span class="weapon-indicator${active ? " active" : ""}"></span>
          <span class="weapon-name">${label} ${active ? "FIRED" : "STBY"}</span>
          <span class="weapon-meta">${timeLabel}</span>
        </div>
      `;
    })
    .join("");
  elements.weaponsActivity.innerHTML = rows;
}

function renderMetricGrid(target, metrics) {
  target.innerHTML = metrics
    .map(
      ([label, value]) => `
        <div class="metric-card">
          <span class="metric-label">${label}</span>
          <strong>${value}</strong>
        </div>
      `
    )
    .join("");
}

function renderPanels() {
  renderMetricGrid(elements.ciws, [
    ["State", state.ciws.state || "-"],
    ["Ammo", state.ciws.ammo_remaining ?? "-"],
    ["Heat", state.ciws.heat != null ? `${Math.round(state.ciws.heat * 100)}%` : "-"],
    ["Spin-Up", state.ciws.spin_up != null ? `${state.ciws.spin_up.toFixed(1)} s` : "-"],
    [
      "Cooldown",
      state.ciws.cooldown_remaining != null
        ? `${state.ciws.cooldown_remaining.toFixed(1)} s`
        : "-",
    ],
    ["Target", state.ciws.active_target_id || "None"],
  ]);

  renderMetricGrid(elements.passive, [
    ["Acoustic", state.passive_tracking.acoustic_state || "-"],
    ["IRST", state.passive_tracking.irst_state || "-"],
    ["Radar", state.passive_tracking.radar_state || "-"],
    ["Active Set", (state.passive_tracking.active_sensors || []).join(", ") || "-"],
    [
      "Radar Blink",
      state.passive_tracking.radar_blink_seconds != null
        ? `${state.passive_tracking.radar_blink_seconds.toFixed(1)} s`
        : "-",
    ],
  ]);

  renderMetricGrid(elements.defenseConfig, [
    ["SAM Ch", state.defense_config.missile_channels ?? "-"],
    ["Jammer Ch", state.defense_config.jammer_channels ?? "-"],
    ["CIWS Ch", state.defense_config.ciws_channels ?? "-"],
    ["Active Sensors", (state.defense_config.active_sensors || []).join(", ") || "-"],
    ["High Priority", state.defense_config.high_priority_doctrine || "-"],
    ["Standard", state.defense_config.standard_doctrine || "-"],
    ["Hold Fire <", state.defense_config.hold_fire_below_score ?? "-"],
  ]);

  renderMetricGrid(
    elements.sam,
    state.samBatteries.map((battery) => [
      `${battery.id}`,
      `${battery.ammo_remaining} rds / ${battery.max_channels} ch / ${battery.status}`,
    ]),
  );

  renderMetricGrid(
    elements.zones,
    state.defendedZones.map((zone) => [
      `${zone.name}`,
      `${zone.health}% / ${zone.status}`,
    ]),
  );
}

function renderTrackDetail() {
  const track = state.tracks.find((item) => item.id === state.selectedTrackId);
  if (!track) {
    elements.detail.innerHTML = `
      <div class="detail-empty">Select a track to inspect shield reasoning.</div>
    `;
    return;
  }

  const reasons = (track.threat_reasons || [])
    .map((reason) => `<li>${reason}</li>`)
    .join("");

  elements.detail.innerHTML = `
    <div class="detail-header">
      <h3>${track.id}</h3>
      <span class="state-pill fusion-${(track.fusion_state || "silent").toLowerCase()}">${track.fusion_state || "-"}</span>
    </div>
    <div class="detail-grid">
      <div class="detail-card">
        <span class="metric-label">Threat Profile</span>
        <strong class="threat-profile">${threatProfileLabel(track)}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Altitude</span>
        <strong>${Math.round(track.altitude_m || estimatedAltitude(track))} m</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Track Confidence</span>
        <strong>${track.track_confidence ?? 0}%</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Shot Doctrine</span>
        <strong>${track.shot_doctrine || "-"}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Shots Planned</span>
        <strong>${track.shots_planned ?? "-"}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Assigned Effector</span>
        <strong>${renderEffectorLabel(track)}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">SAM Battery</span>
        <strong>${track.assigned_battery || "-"}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Target Status</span>
        <strong>${track.target_status || "-"}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Damage</span>
        <strong>${damageLabel(track)}</strong>
      </div>
      <div class="detail-card">
        <span class="metric-label">Engagement</span>
        <strong>${track.engagement_state || "-"}</strong>
      </div>
    </div>
    <div class="detail-reasons">
      <span class="metric-label">Threat Reasons</span>
      <ul>${reasons || "<li>No reasoning available.</li>"}</ul>
    </div>
    <div class="detail-reasons">
      <span class="metric-label">Confidence Reasons</span>
      <ul>${(track.confidence_reasons || []).map((reason) => `<li>${reason}</li>`).join("") || "<li>No confidence reasoning available.</li>"}</ul>
    </div>
  `;
}

function threatProfileLabel(track) {
  if (track.type === "CRUISE_MISSILE") {
    return "Low-altitude sneaky threat";
  }
  if (track.type === "BALLISTIC_MISSILE") {
    return "High-speed short-reaction threat";
  }
  if (track.type === "JET") {
    return "Maneuvering aircraft threat";
  }
  return track.type || "-";
}

function damageLabel(track) {
  const maxHealth = Math.max(1, Number(track.target_max_health ?? track.target_health ?? 100));
  const health = Math.max(0, Math.min(maxHealth, Number(track.target_health ?? 0)));
  const damage = Math.round(((maxHealth - health) / maxHealth) * 100);
  const status = (track.target_status || "").toUpperCase();
  if (status === "DESTROYED") {
    return `100% damage / destroyed`;
  }
  if (status === "NEUTRALIZED") {
    return `100% damage / neutralized`;
  }
  if (status === "ABORTING") {
    return `${damage}% damage / aborting`;
  }
  if (status === "RETREAT") {
    return `${damage}% damage / retreating`;
  }
  if (damage <= 0) {
    return "0% damage / intact";
  }
  return `${damage}% damage / ${health}/${maxHealth} hp`;
}

function renderDamageIndicator(track) {
  const maxHealth = Math.max(1, Number(track.target_max_health ?? track.target_health ?? 100));
  const health = Math.max(0, Math.min(maxHealth, Number(track.target_health ?? 0)));
  const damage = Math.round(((maxHealth - health) / maxHealth) * 100);
  const stateClass = (track.target_status || "unknown").toLowerCase().replaceAll("_", "-");
  return `
    <div class="damage-cell">
      <span>${damage}%</span>
      <span class="state-pill status-${stateClass}">${health}/${maxHealth} hp</span>
    </div>
  `;
}

function renderEffectorLabel(track) {
  if (track.assigned_effector === "SAM" && track.assigned_battery) {
    return `SAM ${track.assigned_battery}`;
  }
  return track.assigned_effector || "-";
}

function renderReport() {
  if (!state.report.outcome) {
    elements.report.innerHTML = "";
    return;
  }

  const findings = (state.report.findings || []).map((item) => `<li>${item}</li>`).join("");
  const recommendations = (state.report.recommendations || [])
    .map((item) => `<li>${item}</li>`)
    .join("");
  const metrics = Object.entries(state.report.metrics || {})
    .map(
      ([key, value]) => `
        <div class="detail-card">
          <span class="metric-label">${key.replaceAll("_", " ")}</span>
          <strong>${value}</strong>
        </div>
      `,
    )
    .join("");
  const hostileHistory = (state.report.hostile_history || [])
    .map(
      (track) => `
        <tr>
          <td>${track.id}</td>
          <td>${track.type}</td>
          <td><span class="state-pill status-${track.final_status.toLowerCase().replaceAll("_", "-")}">${track.final_status}</span></td>
          <td>${Math.round(((Math.max(1, track.target_max_health || track.target_health || 100) - track.target_health) / Math.max(1, track.target_max_health || track.target_health || 100)) * 100)}%</td>
          <td>${track.engagement_state}</td>
        </tr>
      `,
    )
    .join("");

  elements.report.innerHTML = `
    <div class="detail-header">
      <h3>${state.report.title || "Post-Simulation Assessment"}</h3>
      <span class="state-pill status-${(state.report.outcome || "unknown").toLowerCase()}">${state.report.outcome_label || state.report.outcome}</span>
    </div>
    <p class="report-summary">${state.report.executive_summary || ""}</p>
    <div class="detail-grid">${metrics}</div>
    <div class="detail-reasons">
      <span class="metric-label">Findings</span>
      <ul>${findings}</ul>
    </div>
    <div class="detail-reasons">
      <span class="metric-label">Recommendations</span>
      <ul>${recommendations}</ul>
    </div>
    <div class="detail-reasons report-history">
      <span class="metric-label">Hostile History</span>
      <div class="table-wrap">
        <table class="report-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Type</th>
              <th>Final Status</th>
              <th>Damage</th>
              <th>Engagement</th>
            </tr>
          </thead>
          <tbody>${hostileHistory || '<tr><td colspan="5">No hostile history recorded.</td></tr>'}</tbody>
        </table>
      </div>
    </div>
  `;
}

function render() {
  const selectedTrack = state.tracks.find((track) => track.id === state.selectedTrackId) || null;
  renderSummary();
  renderPaneLabels();
  renderTrackTable();
  renderEvents();
  renderBattleLog();
  renderWeaponsActivity();
  renderPanels();
  renderTrackDetail();
  renderReport();
  renderMapHelper();
  const visibleActiveTracks = visibleTracks().filter((track) => !["NEUTRALIZED", "DESTROYED"].includes(track.target_status));
  renderer.draw(
    visibleActiveTracks,
    state.defendedZones,
    state.samBatteries,
    state.showBatteryCoverage,
    state.showConfidenceRings,
    currentTacticalRange(),
    state.selectedTrackId,
  );
  eoirRenderer.draw(selectedTrack, state.eoirMode, state.scenario.status === "RUNNING");
  radarProfileRenderer.draw(visibleActiveTracks, selectedTrack, state.defendedZones);
}

function animateWeaponFeeds(now) {
  const scenarioRunning = state.scenario.status === "RUNNING";
  if (!scenarioRunning) {
    missileFeedRenderer.stop();
    ciwsFeedRenderer.stop();
  }
  const missileActive =
    scenarioRunning && (
      state.tracks.some(
      (track) =>
        track.assigned_effector === "SAM" &&
        ["ASSIGNED", "ENGAGING", "HIT", "KILL_ASSESS"].includes(track.target_status),
      ) || missileFeedRenderer.isActive(now)
    );
  const ciwsTargeting =
    scenarioRunning && (
      state.ciws.state === "FIRING" ||
      state.tracks.some((track) => track.assigned_effector === "CIWS" && track.target_status !== "DESTROYED")
    );
  const ciwsActive = scenarioRunning && (ciwsTargeting || ciwsFeedRenderer.isActive(now));

  missileFeedRenderer.draw(now, { active: missileActive });
  ciwsFeedRenderer.draw(now, { active: ciwsActive, targeting: ciwsTargeting });
  window.requestAnimationFrame(animateWeaponFeeds);
}

function connect() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

  socket.addEventListener("open", () => {
    elements.connection.textContent = "Online";
    elements.connection.classList.remove("offline");
    elements.connection.classList.add("online");
  });

  socket.addEventListener("message", (event) => {
    try {
      applyMessage(JSON.parse(event.data));
    } catch (error) {
      pushSystemEvent("warning", `Dropped unreadable WebSocket frame: ${error.message}.`);
      render();
    }
  });

  socket.addEventListener("close", () => {
    elements.connection.textContent = "Offline";
    elements.connection.classList.remove("online");
    elements.connection.classList.add("offline");
    window.setTimeout(connect, 1500);
  });
}

async function stopSimulation() {
  try {
    const response = await fetch("/control/stop", { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to stop simulation: ${error.message}.`);
    render();
  }
}

async function togglePauseSimulation() {
  const endpoint = state.scenario.execution_state === "PAUSED" ? "/control/resume" : "/control/pause";
  try {
    const response = await fetch(endpoint, { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to change pause state: ${error.message}.`);
    render();
  }
}

async function stepSimulation() {
  try {
    const response = await fetch("/control/step", { method: "POST" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to step simulation: ${error.message}.`);
    render();
  }
}

async function resetSimulation() {
  try {
    const response = await fetch("/control/reset", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_name: elements.scenarioSelect.value || state.scenario.name }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to reset simulation: ${error.message}.`);
    render();
  }
}

async function reloadScenarioConfig() {
  try {
    const response = await fetch("/control/reload", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_name: elements.scenarioSelect.value || state.scenario.name }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to reload scenario config: ${error.message}.`);
    render();
  }
}

async function exportBattleLog() {
  try {
    const response = await fetch("/control/export/battle-log");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.scenario.name || "scenario"}-battle-log.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    pushSystemEvent("warning", `Failed to export battle log: ${error.message}.`);
    render();
  }
}

async function exportReport() {
  try {
    const response = await fetch("/control/export/report");
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const payload = await response.json();
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.scenario.name || "scenario"}-report.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    pushSystemEvent("warning", `Failed to export report: ${error.message}.`);
    render();
  }
}

async function setDoctrineMode() {
  try {
    const response = await fetch("/control/doctrine", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ doctrine_mode: elements.doctrineSelect.value || state.scenario.doctrine_mode }),
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
  } catch (error) {
    pushSystemEvent("warning", `Failed to set doctrine mode: ${error.message}.`);
    render();
  }
}

initFilters();
elements.stopButton.addEventListener("click", stopSimulation);
elements.pauseButton.addEventListener("click", togglePauseSimulation);
elements.stepButton.addEventListener("click", stepSimulation);
elements.resetButton.addEventListener("click", resetSimulation);
elements.reloadButton.addEventListener("click", reloadScenarioConfig);
elements.reportExportButton.addEventListener("click", exportReport);
elements.battleLogExportButton.addEventListener("click", exportBattleLog);
elements.doctrineSelect.addEventListener("change", setDoctrineMode);
elements.eoirModeSelect.addEventListener("change", () => {
  state.eoirMode = elements.eoirModeSelect.value || "EO";
  render();
});
elements.battleLogCategoryFilter.addEventListener("change", () => {
  state.battleLogCategoryFilter = elements.battleLogCategoryFilter.value || "ALL";
  renderBattleLog();
});
elements.battleLogTrackFilter.addEventListener("change", () => {
  state.battleLogTrackFilter = elements.battleLogTrackFilter.value || "ALL";
  renderBattleLog();
});
elements.canvas.addEventListener("mousemove", (event) => {
  state.mapCursor = { ...canvasPointToWorld(elements.canvas, event.clientX, event.clientY), active: true };
  renderMapHelper();
});
elements.canvas.addEventListener("mouseleave", () => {
  state.mapCursor = { x: 0, y: 0, active: false };
  renderMapHelper();
});
elements.canvas.addEventListener("click", (event) => {
  state.mapSelection = canvasPointToWorld(elements.canvas, event.clientX, event.clientY);
  renderMapHelper();
});
elements.coverageToggleButton.addEventListener("click", () => {
  state.showBatteryCoverage = !state.showBatteryCoverage;
  render();
});
elements.confidenceToggleButton.addEventListener("click", () => {
  state.showConfidenceRings = !state.showConfidenceRings;
  render();
});
elements.zoomSelect.addEventListener("change", () => {
  state.tacticalScale = elements.zoomSelect.value || "AUTO";
  render();
});
elements.copyCoordinatesButton.addEventListener("click", async () => {
  if (!state.mapSelection) {
    return;
  }
  const text = `"position": { "x": ${state.mapSelection.x}, "y": ${state.mapSelection.y} }`;
  try {
    await navigator.clipboard.writeText(text);
    pushSystemEvent("info", `Copied coordinates: ${text}`);
    render();
  } catch (error) {
    pushSystemEvent("warning", `Failed to copy coordinates: ${error.message}.`);
    render();
  }
});
render();
connect();
window.requestAnimationFrame(animateWeaponFeeds);
