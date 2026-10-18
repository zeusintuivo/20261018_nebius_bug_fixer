const STAGES = ["intake", "qualify", "blackbox", "oracle", "diff_inspect", "deploy"];

const lanesEl = document.getElementById("lanes");
const auditEl = document.getElementById("audit");
const escalEl = document.getElementById("escal");
const ticker = document.getElementById("ticker");

let bugs = [];

async function init() {
  bugs = await (await fetch("/api/bugs")).json();
  renderLanes();
  connectStream();
  refreshSidebars();
}

function renderLanes() {
  lanesEl.innerHTML = "";
  for (const b of bugs) {
    const row = document.createElement("div");
    row.className = "lane";
    row.id = `lane-${b.id}`;
    row.innerHTML = `
      <div class="title">${b.id}<small>${b.title}</small></div>
      ${STAGES.map(s => `<div class="cell" data-stage="${s}">·</div>`).join("")}
      <div class="outcome pending">pending</div>
    `;
    lanesEl.appendChild(row);
  }
}

function updateLane(ev) {
  if (ev.bug_id === "*") return;
  const lane = document.getElementById(`lane-${ev.bug_id}`);
  if (!lane) return;
  lane.classList.add("active");

  if (ev.stage === "start") {
    lane.querySelectorAll(".cell").forEach(c => { c.className = "cell"; c.textContent = "·"; });
    lane.querySelector(".outcome").className = "outcome pending";
    lane.querySelector(".outcome").textContent = "running…";
    return;
  }
  if (ev.stage === "shipped") {
    lane.querySelector(".outcome").className = "outcome shipped";
    lane.querySelector(".outcome").textContent = "✓ shipped";
    ticker.textContent = `${ev.bug_id} shipped unattended`;
    return;
  }
  if (ev.stage === "escalate") {
    lane.querySelector(".outcome").className = "outcome escalated";
    lane.querySelector(".outcome").textContent = "⚑ escalated";
    ticker.textContent = `${ev.bug_id} refused by the line — human notified`;
    refreshSidebars();
    return;
  }

  const cell = lane.querySelector(`.cell[data-stage="${ev.stage}"]`);
  if (cell) {
    cell.className = `cell ${ev.status}`;
    cell.textContent = ev.status.toUpperCase();
    cell.title = ev.detail || "";
  }
  ticker.textContent = `${ev.bug_id} · ${ev.stage} → ${ev.status}`;
}

function connectStream() {
  const es = new EventSource("/api/stream");
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    updateLane(ev);
    // audit side-updates
    if (["shipped", "escalate"].includes(ev.stage)) setTimeout(refreshSidebars, 150);
    else if (ev.stage === "deploy" && ev.status === "pass") setTimeout(refreshSidebars, 150);
  };
  es.onerror = () => { ticker.textContent = "stream dropped — refresh"; };
}

async function refreshSidebars() {
  const [audit, escal] = await Promise.all([
    fetch("/api/audit").then(r => r.json()),
    fetch("/api/escalations").then(r => r.json()),
  ]);
  auditEl.textContent = audit.slice(-25).map(a =>
    `${new Date(a.ts * 1000).toLocaleTimeString()}  ${a.bug_id.padEnd(6)}  ${a.event.padEnd(22)}  #${a.hash}`
  ).join("\n");
  auditEl.scrollTop = auditEl.scrollHeight;

  escalEl.innerHTML = escal.map(e => `
    <div class="item">
      <b>${e.bug.id}</b> — ${e.bug.title}
      <small>${e.reason}</small>
    </div>
  `).join("") || `<div class="hint">none yet</div>`;
}

document.getElementById("runAll").onclick = () => fetch("/api/run_all", { method: "POST" });
document.getElementById("reset").onclick = async () => {
  await fetch("/api/reset", { method: "POST" });
  renderLanes(); refreshSidebars();
};

init();
