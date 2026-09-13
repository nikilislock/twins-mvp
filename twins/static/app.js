"use strict";

// The server owns every state transition. The browser draws observed data only.
const $ = (id) => document.getElementById(id);
const COLORS = ["#d2df75", "#9faef5"];
const PHASES = ["baseline", "familiarization", "recognition", "communication", "separation", "reunion"];
const PHASE_NAMES = { baseline: "Özdeş başlangıç", familiarization: "Birlikte deneyim", recognition: "İpucu tanıma testi", communication: "Sembolik görev", separation: "Ayrı deneyimler", reunion: "Yeniden buluşma" };
const EVENT_NAMES = { initialized: "BAŞLANGIÇ", initialization: "BAŞLANGIÇ", phase: "FAZ DEĞİŞİMİ", phase_change: "FAZ DEĞİŞİMİ", recognition: "TANIMA PROBU", communication: "İŞARET DENEMESİ", signal: "İŞARET DENEMESİ", plasticity: "ÖĞRENME", shuffle: "KANAL KONTROLÜ", silence: "NÖRAL MÜDAHALE", completed: "PROTOKOL BİTTİ" };
let state = null;
let connected = false;
let pendingControl = false;
let zoom = 1;
let cue = "partner";
let replay = null;
let lastEventKey = "";
let toastTimer;
let replayTimer;
let replayRequest = 0;
let stateRevision = 0;
const clamp = (n, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, Number(n) || 0));
const numeric = (n) => typeof n === "number" && Number.isFinite(n);
const fixed = (n, places = 2) => numeric(n) ? n.toFixed(places) : "—";
const percent = (n) => numeric(n) ? `${Math.round(clamp(n) * 100)}%` : "—";
const count = (n) => numeric(n) ? new Intl.NumberFormat("tr-TR").format(n) : "—";
const setText = (id, value) => { const element = $(id); if (element) element.textContent = value; };

function toast(message) {
  clearTimeout(toastTimer);
  setText("toast", message);
  $("toast").classList.add("visible");
  toastTimer = setTimeout(() => $("toast").classList.remove("visible"), 5000);
}

async function request(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options, signal: AbortSignal.timeout(20000) });
  if (!response.ok) {
    let message = `Sunucu yanıtı: ${response.status}`;
    try { const data = await response.json(); message = typeof data.detail === "string" ? data.detail : message; } catch (_) { /* Preserve status when body is not JSON. */ }
    throw new Error(message);
  }
  return response.json();
}

function setAvailability() {
  const disabled = !connected || pendingControl || Boolean(replay);
  ["play-button", "step-button", "reset-button", "speed", "plasticity-toggle", "shuffle-toggle", "silence-toggle"].forEach(id => { if ($(id)) $(id).disabled = disabled; });
  document.querySelectorAll("[data-phase]").forEach(button => button.disabled = disabled);
  $("neuron-id").disabled = Boolean(replay) || !connected;
  $("neuron-form").querySelector("button").disabled = Boolean(replay) || !connected;
  $("arrays-link")?.setAttribute("aria-disabled", String(Boolean(replay)));
}

async function control(action, value, extra = {}) {
  if (pendingControl || replay) return;
  pendingControl = true;
  stateRevision++;
  setAvailability();
  try {
    const result = await request("/api/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, value, ...extra }) });
    connected = true;
    state = result;
    render();
  } catch (error) { toast(`İşlem uygulanamadı: ${error.message}`); }
  finally { pendingControl = false; setAvailability(); }
}

async function poll() {
  if (!replay && !pendingControl) {
    try {
      const revision = stateRevision;
      const result = await request("/api/state");
      if (revision !== stateRevision || replay) return setTimeout(poll, 500);
      state = result;
      connected = true;
      render();
    } catch (_) {
      connected = false;
      $("connection-dot").className = "status-dot disconnected";
      setText("connection-text", state ? "Bağlantı kesildi · son kayıt gösteriliyor" : "Sunucuya ulaşılamıyor");
      if (!state) {
        $("arena-empty").hidden = false;
        $("arena-empty").querySelector("strong").textContent = "Simülasyon bağlantısı bekleniyor";
        $("arena-empty").querySelector("span:last-child").textContent = "Yerel sunucunun çalıştığını kontrol et.";
      }
      setAvailability();
    }
  }
  setTimeout(poll, 500);
}

function render() {
  if (!state) return;
  const topology = state.topology || {};
  const twins = state.twins || [];
  const metrics = state.metrics || {};
  $("arena-empty").hidden = twins.length > 0;
  $("connection-dot").className = `status-dot${state.error ? " disconnected" : state.running && !replay ? "" : " waiting"}`;
  setText("connection-text", replay ? "Kayıttan izleniyor · canlı deney duraklatıldı" : state.error ? `Hata · ${state.error}` : state.running ? "Canlı simülasyon" : state.protocol?.completed ? "Protokol tamamlandı" : "Simülasyon duraklatıldı");
  setText("clock", `${fixed((state.neural_ms || 0) / 1000, 3)} s nöral`);
  setText("run-short", String(replay?.id || state.run_id || "—").slice(0, 8).toUpperCase());
  setText("tick", count(state.tick));
  setText("seed", state.seed ?? "—");
  setText("dt", "1 ms");
  setText("phase-description", PHASE_NAMES[state.phase] || state.phase || "—");
  const phaseIndex = PHASES.indexOf(state.phase);
  document.querySelectorAll("[data-phase]").forEach((button, index) => {
    button.classList.toggle("active", button.dataset.phase === state.phase);
    button.classList.toggle("complete", index < phaseIndex);
    button.setAttribute("aria-pressed", String(button.dataset.phase === state.phase));
  });
  const play = $("play-button");
  play.classList.toggle("running", Boolean(state.running));
  play.querySelector("span").textContent = state.running ? "Duraklat" : "Başlat";
  play.querySelector("path").setAttribute("d", state.running ? "M7 4v12M13 4v12" : "m7 4 9 6-9 6Z");
  $("plasticity-toggle").checked = Boolean(state.plasticity);
  $("shuffle-toggle").checked = Boolean(state.shuffle_signals);
  if ($("silence-toggle")) $("silence-toggle").checked = Boolean(state.neural_silenced);
  if (state.speed) $("speed").value = String(state.speed);
  setText("neuron-count", count(topology.neuron_count ?? topology.neurons));
  setText("edge-count", count(topology.edge_count ?? topology.edges));
  setText("topology-label", topology.synthetic ? "Sentetik test ağı" : topology.graph_mode === "full" ? "FlyWire · tam ağ" : "FlyWire · alt ağ");
  const isAnatomical = Boolean(topology.layout?.includes("FlyWire"));
  setText("brain-sampling", isAnatomical ? "ANOTASYON · XY İZDÜŞÜMÜ" : "ŞEMATİK ÖRNEKLEM");
  document.querySelector(".brain-layout-note").textContent = isAnatomical ? "Anotasyon konumları · ağ örneklemi" : "Yerleşim anatomik değildir";
  setText("origin-status", topology.initial_states_identical ? "Özdeş başlangıç doğrulandı" : "Başlangıç eşitliği doğrulanmadı");
  setText("origin-fingerprint", topology.initial_state_hash ? `SHA-256 ${topology.initial_state_hash.slice(0, 22)}…` : "Başlangıç özeti bulunamadı");
  $("origin-fingerprint").title = topology.initial_state_hash || "";
  setText("origin-check", topology.initial_states_identical ? "✓" : "?");
  twins.forEach((twin, index) => {
    const prefix = index ? "eve2" : "eve";
    setText(`${prefix}-reward`, percent(twin.energy));
    setText(`${prefix}-activity`, `${fixed(twin.spike_rate, 1)} Hz`);
    setText(`${prefix}-spikes`, `${count(twin.spike_count)} spike`);
  });
  setText("divergence-value", fixed(metrics.divergence, 3));
  setText("voltage-distance", `${fixed(metrics.state_distance, 2)} mV · voltaj RMS farkı`);
  setText("communication-accuracy", percent(metrics.communication_accuracy));
  setText("communication-trials", `${count(metrics.trial_count ?? 0)} deneme`);
  setText("last-symbol", state.channel?.last_trial ? (state.channel.symbols?.[state.channel.last_trial.symbol] ?? "—") : "—");
  const last = state.channel?.last_trial;
  setText("trial-window", count(metrics.trial_window || 0));
  setText("signal-sender", last?.sender === "B" ? "EVE II" : "EVE");
  setText("signal-receiver", last?.sender === "B" ? "EVE" : "EVE II");
  setText("trial-detail", last ? `#${count(last.trial)} · K${last.context + 1} → ${state.channel.symbols[last.symbol]} → seçim ${last.action + 1} · ödül ${last.reward}${last.shuffled ? " · kanal karışık" : ""}` : "Henüz deneme yok");
  setText("gate-a", fixed(twins[0]?.neural_gate, 2));
  setText("gate-b", fixed(twins[1]?.neural_gate, 2));
  $("export-link").href = replay ? `/api/runs/${encodeURIComponent(replay.id)}/export` : "/api/export";
  $("last-symbol").title = last ? `Gönderici ${last.sender}; koşul ${last.context}; alınan ${last.received_symbol}; eylem ${last.action}; ödül ${last.reward}` : "Henüz bir işaret denemesi yok";
  renderRecognition();
  renderMatrix();
  renderEvents();
  drawAll();
  setAvailability();
  const sources = `${topology.source || "Kaynak belirtilmedi"}. ${count(topology.neuron_count)} nöron ve ${count(topology.edge_count)} yönlü bağlantı. Veri lisansı: ${topology.data_license || "kaynak belgesine bakın"}.`;
  setText("methods-topology", sources);
  setText("methods-provenance", `Connectome SHA-256: ${topology.graph_hash || topology.fingerprint || "—"}\nKaynak sürümü: ${topology.source_commit || "—"}`);
}

function renderRecognition() {
  if (!state) return;
  let difference = 0;
  let n = 0;
  (state.twins || []).forEach((twin, index) => {
    const key = index ? "b" : "a";
    const value = twin.recognition?.[cue];
    $(`recognition-${key}`).style.width = `${clamp(value) * 100}%`;
    setText(`recognition-${key}-value`, fixed(value, 2));
    if (numeric(twin.recognition?.partner) && numeric(twin.recognition?.novel)) { difference += twin.recognition.partner - twin.recognition.novel; n++; }
  });
  setText("recognition-score", n ? `${difference >= 0 ? "+" : ""}${fixed(difference / n, 2)}` : "—");
  setText("recognition-copy", cue === "identical_cue" ? "Kontrol: partnerle aynı ipucunu taşıyan yabancı" : cue === "novel" ? "Eğitimdeki karşıt ipucunun tanıdıklık skoru" : "Partner ipucuna verilen tanıdıklık skoru");
  document.querySelectorAll("[data-cue]").forEach(button => { button.classList.toggle("selected", button.dataset.cue === cue); button.setAttribute("aria-pressed", String(button.dataset.cue === cue)); });
}

function renderMatrix() {
  const [agentIndex, role] = ($("matrix-role")?.value || "0:sender").split(":");
  const matrix = state?.twins?.[Number(agentIndex)]?.weights?.[role];
  setText("matrix-axis", role === "sender" ? "GÖNDERİLEN SEMBOL" : "SEÇİLEN EYLEM");
  document.querySelector(".matrix-y-label").textContent = role === "sender" ? "KOŞUL" : "ALINAN SEMBOL";
  const grid = $("symbol-matrix");
  if (!grid.children.length) {
    for (let i = 0; i < 16; i++) { const cell = document.createElement("div"); cell.className = "matrix-cell"; grid.append(cell); }
  }
  for (let i = 0; i < 16; i++) {
    const value = matrix?.[Math.floor(i / 4)]?.[i % 4];
    const cell = grid.children[i];
    cell.textContent = numeric(value) ? value.toFixed(2) : "—";
    cell.style.background = numeric(value) ? `rgba(210,223,117,${.035 + clamp(value) * .65})` : "#2b3224";
    cell.style.color = numeric(value) && value > .48 ? "#edf0e4" : "#949e8a";
    cell.title = `${agentIndex === "0" ? "EVE" : "EVE II"} ${role}: satır ${Math.floor(i / 4) + 1}, sütun ${i % 4 + 1}: ${numeric(value) ? percent(value) : "veri yok"}`;
  }
}

function renderEvents() {
  const events = state.events || [];
  const key = `${state.run_id || replay?.id}:${events.length}:${events.at(-1)?.id}:${events.at(-1)?.tick}:${state.tick === 0}`;
  if (key === lastEventKey) return;
  lastEventKey = key;
  setText("event-count", `${count(events.length)} OLAY`);
  const fragment = document.createDocumentFragment();
  for (const event of [...events].reverse().slice(0, 80)) {
    const row = document.createElement("div"); row.className = "event-row";
    const time = document.createElement("span"); time.className = "event-time"; time.textContent = `#${count(event.tick)}`;
    const kind = document.createElement("span"); kind.className = "event-type"; kind.textContent = EVENT_NAMES[event.kind] || String(event.kind || "OLAY").replaceAll("_", " ").toLocaleUpperCase("tr");
    const description = document.createElement("span"); description.className = "event-description"; description.textContent = event.message || "—";
    row.append(time, kind, description); fragment.append(row);
  }
  if (!events.length) { const empty = document.createElement("div"); empty.className = "journal-empty"; empty.textContent = "Bu adımda kayıtlı olay bulunmuyor."; fragment.append(empty); }
  $("event-log").replaceChildren(fragment);
}

function canvasContext(id) {
  const canvas = $(id);
  const rect = canvas.getBoundingClientRect();
  const ratio = Math.min(devicePixelRatio || 1, 2);
  const width = Math.round(rect.width * ratio), height = Math.round(rect.height * ratio);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  return { ctx: context, w: rect.width, h: rect.height };
}

function drawArena() {
  const { ctx, w, h } = canvasContext("arena-canvas");
  ctx.fillStyle = "#151b12"; ctx.fillRect(0, 0, w, h);
  const padX = 38, padY = 32;
  const sx = w - padX * 2, sy = h - padY * 2;
  const point = (x, y) => [w / 2 + (x - .5) * sx * zoom, h / 2 + (y - .5) * sy * zoom];
  ctx.fillStyle = "#3b4631";
  for (let x = 0; x <= 24; x++) for (let y = 0; y <= 14; y++) { const p = point(x / 24, y / 14); ctx.globalAlpha = .6; ctx.fillRect(p[0], p[1], .85, .85); }
  ctx.globalAlpha = 1;
  const start = point(0, 0), end = point(1, 1);
  ctx.strokeStyle = "#36412b"; ctx.lineWidth = 1;
  ctx.strokeRect(start[0], start[1], end[0] - start[0], end[1] - start[1]);
  const corners = [[start[0], start[1], 1, 1], [end[0], start[1], -1, 1], [start[0], end[1], 1, -1], [end[0], end[1], -1, -1]];
  ctx.strokeStyle = "#68784b";
  for (const [x, y, dx, dy] of corners) { ctx.beginPath(); ctx.moveTo(x + dx * 9, y); ctx.lineTo(x, y); ctx.lineTo(x, y + dy * 9); ctx.stroke(); }
  if (!state) return;
  if (state.arena?.separated) {
    ctx.setLineDash([5, 6]); ctx.strokeStyle = "#8b967458"; ctx.beginPath(); ctx.moveTo(w / 2, start[1]); ctx.lineTo(w / 2, end[1]); ctx.stroke(); ctx.setLineDash([]);
    ctx.font = "7px 'Segoe UI',sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = "#8f9b80"; ctx.fillText("AYRILMA BARİYERİ", w / 2, start[1] - 11);
  }
  (state.arena?.resources || []).forEach(resource => {
    const [x, y] = point(resource.x, resource.y);
    ctx.strokeStyle = "#576443"; ctx.fillStyle = "#d2df7507"; ctx.beginPath(); ctx.arc(x, y, 20 * zoom, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.setLineDash([2, 4]); ctx.strokeStyle = "#465338"; ctx.beginPath(); ctx.arc(x, y, 29 * zoom, 0, Math.PI * 2); ctx.stroke(); ctx.setLineDash([]);
    ctx.save(); ctx.translate(x, y); ctx.rotate(Math.PI / 4); ctx.strokeStyle = "#92a168"; ctx.strokeRect(-3, -3, 6, 6); ctx.restore();
    ctx.font = "7px Consolas,monospace"; ctx.textAlign = "center"; ctx.fillStyle = "#687752"; ctx.fillText(`K${Number(resource.context) + 1}`, x, y + 41 * zoom);
  });
  (state.twins || []).forEach((twin, index) => {
    const color = COLORS[index];
    const trail = twin.trail || [];
    ctx.lineWidth = 1.2;
    for (let i = 1; i < trail.length; i++) {
      const a = point(trail[i - 1].x, trail[i - 1].y), b = point(trail[i].x, trail[i].y);
      ctx.globalAlpha = .1 + .65 * i / trail.length; ctx.strokeStyle = color; ctx.beginPath(); ctx.moveTo(...a); ctx.lineTo(...b); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    const [x, y] = point(twin.x, twin.y);
    ctx.fillStyle = color + "09"; ctx.strokeStyle = color + "25"; ctx.beginPath(); ctx.arc(x, y, 28, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.save(); ctx.translate(x, y); ctx.rotate(twin.heading || 0);
    ctx.strokeStyle = color + "55"; ctx.fillStyle = color + "13"; ctx.beginPath(); ctx.ellipse(-2, -5, 8, 3, -.35, 0, Math.PI * 2); ctx.ellipse(-2, 5, 8, 3, .35, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    ctx.fillStyle = color; ctx.beginPath(); ctx.ellipse(0, 0, 6, 2.3, 0, 0, Math.PI * 2); ctx.fill(); ctx.beginPath(); ctx.arc(6, 0, 2.6, 0, Math.PI * 2); ctx.fill();
    ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(8, -1); ctx.lineTo(12, -4); ctx.moveTo(8, 1); ctx.lineTo(12, 4); ctx.stroke();
    ctx.restore();
    ctx.font = "9px 'Segoe UI',sans-serif"; ctx.textAlign = "center"; ctx.fillStyle = color; ctx.fillText(index ? "EVE II" : "EVE", x, y - 35);
  });
}

function drawBrain(id, index) {
  const { ctx, w, h } = canvasContext(id);
  const activity = state?.twins?.[index]?.activity || [];
  const color = COLORS[index];
  const p = (node) => [13 + node.x * (w - 26), 12 + node.y * (h - 27)];
  ctx.strokeStyle = "#303a2780"; ctx.setLineDash([2, 5]); ctx.beginPath(); ctx.moveTo(w / 2, 8); ctx.lineTo(w / 2, h - 10); ctx.stroke(); ctx.setLineDash([]);
  const nodes = new Map(activity.map(node => [node.index, node]));
  for (const edge of state?.topology?.sample_edges || []) {
    const a = nodes.get(edge.source), b = nodes.get(edge.target);
    if (!a || !b) continue;
    const active = a.active || (a.trace || 0) > .15;
    ctx.strokeStyle = active ? color + "45" : "#59634b25"; ctx.lineWidth = active ? .65 : .45;
    ctx.beginPath(); ctx.moveTo(...p(a)); ctx.lineTo(...p(b)); ctx.stroke();
  }
  for (const node of activity) {
    const [x, y] = p(node);
    const intensity = node.active ? 1 : clamp(node.trace || 0);
    if (intensity > .05) { ctx.fillStyle = color + "12"; ctx.beginPath(); ctx.arc(x, y, 3 + intensity * 4, 0, Math.PI * 2); ctx.fill(); }
    ctx.beginPath(); ctx.arc(x, y, node.active ? 2.3 : 1.1 + intensity, 0, Math.PI * 2);
    ctx.fillStyle = intensity > .1 ? color : "#84927165"; ctx.fill();
  }
  ctx.font = "6px Consolas,monospace"; ctx.fillStyle = "#68775b"; ctx.textAlign = "left";
  ctx.fillText(activity.length ? `${activity.length} nöron örneği · ${state.topology?.sample_edges?.length || 0} bağlantı` : "CANLI VERİ BEKLENİYOR", 12, h - 3);
}

function drawChart() {
  const { ctx, w, h } = canvasContext("divergence-chart");
  const history = (state?.history || []).filter(item => numeric(item.divergence));
  const padding = 3;
  const top = 8, bottom = h - 5;
  const maxValue = Math.max(.01, ...history.map(item => item.divergence)) * 1.18;
  ctx.font = "6px Consolas,monospace"; ctx.textAlign = "right";
  for (let i = 0; i < 4; i++) {
    const y = top + (bottom - top) * i / 3;
    ctx.strokeStyle = "#343d2b"; ctx.setLineDash([2, 4]); ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle = "#66745b"; ctx.fillText((maxValue * (1 - i / 3)).toFixed(3), w, y - 3);
  }
  if (!history.length) return;
  const first = history[0].tick, last = history.at(-1).tick;
  const x = tick => padding + ((tick - first) / Math.max(1, last - first)) * (w - padding * 2);
  const y = value => bottom - value / maxValue * (bottom - top);
  ctx.beginPath(); ctx.moveTo(x(first), bottom);
  for (const point of history) ctx.lineTo(x(point.tick), y(point.divergence));
  ctx.lineTo(x(last), bottom); ctx.closePath();
  const gradient = ctx.createLinearGradient(0, top, 0, bottom); gradient.addColorStop(0, "#d2df7526"); gradient.addColorStop(1, "#d2df7500"); ctx.fillStyle = gradient; ctx.fill();
  ctx.strokeStyle = COLORS[0]; ctx.lineWidth = 1.4; ctx.beginPath();
  history.forEach((point, i) => i ? ctx.lineTo(x(point.tick), y(point.divergence)) : ctx.moveTo(x(point.tick), y(point.divergence))); ctx.stroke();
  ctx.fillStyle = COLORS[0]; ctx.beginPath(); ctx.arc(x(last), y(history.at(-1).divergence), 2.2, 0, Math.PI * 2); ctx.fill();
  setText("chart-start", `#${count(first)}`); setText("chart-end", `#${count(last)}`);
}

function drawAll() { drawArena(); drawBrain("brain-a", 0); drawBrain("brain-b", 1); drawChart(); }

async function inspectNeuron(value) {
  if (replay) { toast("Tek nöron denetleyicisi canlı durum içindir."); return; }
  setText("neuron-result", "Nöron bilgileri yükleniyor…");
  document.querySelector(".neuron-inspector").open = true;
  try {
    const result = await request(`/api/neurons/${encodeURIComponent(value)}`);
    setText("neuron-result", JSON.stringify(result, null, 2));
  } catch (error) { setText("neuron-result", `Nöron bulunamadı: ${error.message}`); }
}

async function openRuns() {
  $("runs-dialog").showModal();
  setText("runs-list", "Kayıtlar yükleniyor…");
  try {
    const result = await request("/api/runs");
    const runs = Array.isArray(result) ? result : result.runs || [];
    const fragment = document.createDocumentFragment();
    for (const run of runs) {
      const row = document.createElement("div"); row.className = "run-row";
      const info = document.createElement("div"), title = document.createElement("strong"), detail = document.createElement("small");
      title.textContent = run.id;
      detail.textContent = `${new Date(run.created).toLocaleString("tr-TR")} · ${count(run.last_tick)} adım · ${count(run.frames)} kayıt`;
      info.append(title, detail);
      const actions = document.createElement("div"); actions.className = "run-actions";
      const button = document.createElement("button"); button.className = "text-button"; button.textContent = "İzle"; button.addEventListener("click", () => startReplay(run));
      const link = document.createElement("a"); link.href = `/api/runs/${encodeURIComponent(run.id)}/export`; link.download = ""; link.textContent = "İndir ↗";
      actions.append(button, link); row.append(info, actions); fragment.append(row);
    }
    if (!runs.length) { const empty = document.createElement("p"); empty.textContent = "Henüz kayıtlı deney bulunmuyor."; fragment.append(empty); }
    $("runs-list").replaceChildren(fragment);
  } catch (error) { setText("runs-list", `Kayıtlar okunamadı: ${error.message}`); }
}

async function startReplay(run) {
  if (state?.running) await control("pause");
  if (state?.running) { toast("Kayıt izlemek için önce canlı deneyi duraklat."); return; }
  replay = { id: run.id, lastTick: run.last_tick || 0 };
  $("runs-dialog").close();
  $("replay-bar").hidden = false;
  $("replay-tick").max = String(Math.max(1, replay.lastTick));
  $("replay-tick").value = "0";
  setAvailability();
  await loadReplay(0);
  $("workspace").scrollIntoView({ behavior: "smooth" });
}

async function loadReplay(tick) {
  if (!replay) return;
  const id = replay.id;
  const serial = ++replayRequest;
  try {
    const result = await request(`/api/runs/${encodeURIComponent(id)}/state?tick=${encodeURIComponent(tick)}`);
    if (replay?.id !== id || serial !== replayRequest) return;
    state = result.state || result;
    setText("replay-tick-value", count(state.tick));
    render();
  } catch (error) { toast(`Kayıt açılamadı: ${error.message}`); }
}

$("play-button").addEventListener("click", () => control(state?.running ? "pause" : "run"));
$("step-button").addEventListener("click", () => control("step"));
$("reset-button").addEventListener("click", () => { const seed = Number($("seed-input").value); if (!Number.isInteger(seed) || seed < 0 || seed > 2147483647) { toast("Tohum 0–2147483647 arasında tam sayı olmalı."); return; } control("reset", null, { seed }); });
$("matrix-role").addEventListener("change", renderMatrix);
$("speed").addEventListener("change", event => control("speed", Number(event.target.value)));
$("plasticity-toggle").addEventListener("change", event => control("plasticity", event.target.checked));
$("shuffle-toggle").addEventListener("change", event => control("shuffle", event.target.checked));
if ($("silence-toggle")) $("silence-toggle").addEventListener("change", event => control("silence", event.target.checked));
document.querySelectorAll("[data-phase]").forEach(button => button.addEventListener("click", () => control("phase", button.dataset.phase)));
document.querySelectorAll("[data-cue]").forEach(button => button.addEventListener("click", () => { cue = button.dataset.cue; renderRecognition(); }));
$("zoom-in").addEventListener("click", () => { zoom = Math.min(2, zoom + .25); setText("zoom-label", `${zoom.toFixed(1)}×`); drawArena(); });
$("zoom-out").addEventListener("click", () => { zoom = Math.max(.75, zoom - .25); setText("zoom-label", `${zoom.toFixed(1)}×`); drawArena(); });
["methods-open", "methods-footer"].forEach(id => $(id).addEventListener("click", () => $("methods-dialog").showModal()));
document.querySelectorAll(".close-dialog").forEach(button => button.addEventListener("click", () => button.closest("dialog").close()));
document.querySelectorAll("dialog").forEach(dialog => dialog.addEventListener("click", event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } }));
$("runs-button").addEventListener("click", openRuns);
$("replay-tick").addEventListener("input", event => { clearTimeout(replayTimer); const tick = event.target.value; setText("replay-tick-value", count(Number(tick))); replayTimer = setTimeout(() => loadReplay(tick), 120); });
$("return-live").addEventListener("click", async () => { replay = null; $("replay-bar").hidden = true; setAvailability(); try { state = await request("/api/state"); connected = true; render(); } catch (_) { toast("Canlı bağlantı şu anda kullanılamıyor."); } });
$("neuron-form").addEventListener("submit", event => { event.preventDefault(); inspectNeuron($("neuron-id").value.trim()); });
["brain-a", "brain-b"].forEach((id, index) => $(id).addEventListener("click", event => {
  if (replay) { toast("Nöron denetleyicisi canlı durum içindir. Önce canlı deneye dön."); return; }
  const rect = event.currentTarget.getBoundingClientRect();
  const x = event.clientX - rect.left, y = event.clientY - rect.top;
  let nearest = null, distance = 14;
  for (const node of state?.twins?.[index]?.activity || []) { const d = Math.hypot(x - (13 + node.x * (rect.width - 26)), y - (12 + node.y * (rect.height - 27))); if (d < distance) { distance = d; nearest = node; } }
  if (nearest) { $("neuron-id").value = nearest.id; inspectNeuron(nearest.id); }
}));
document.querySelectorAll(".masthead nav a").forEach(link => link.addEventListener("click", () => { document.querySelectorAll(".masthead nav a").forEach(item => item.classList.remove("nav-active")); link.classList.add("nav-active"); }));
document.addEventListener("keydown", event => { if (event.code === "Space" && event.target === document.body && !document.querySelector("dialog[open]")) { event.preventDefault(); if (connected && !replay) control(state?.running ? "pause" : "run"); } });
new ResizeObserver(() => drawAll()).observe($("workspace"));
setAvailability(); renderMatrix(); drawAll(); poll();
