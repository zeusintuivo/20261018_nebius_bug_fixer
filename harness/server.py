"""FastAPI server: SSE stream per pipeline run + control-plane endpoints.

Endpoints the UI will consume:
  GET  /                      → static UI
  GET  /api/bugs              → list seeded bugs
  POST /api/run/{bug_id}      → kick off one pipeline (async, streams via SSE)
  POST /api/run_all           → kick off every bug sequentially
  POST /api/reset             → wipe audit + escalations (demo convenience)
  POST /api/pause             → operator pauses the line
  POST /api/resume            → operator resumes
  GET  /api/line              → line status (paused / running)
  GET  /api/stream            → SSE event stream of pipeline progress
  GET  /api/audit             → full audit log (hash-chained + HMAC-signed)
  GET  /api/audit/verify      → re-walks chain, proves no tampering
  GET  /api/audit/replay/{bug_id}
                              → every audit event for one bug (replay a decision)
  GET  /api/escalations       → inbox of handed-to-human bugs
  GET  /api/metrics           → line health counters
  GET  /api/policy            → the interlocks, as data
"""
from __future__ import annotations
import asyncio, json, queue, threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
from pipeline import (  # noqa: E402
    run_pipeline, BUGS, AUDIT, ESCALATIONS,
    verify_audit, replay, metrics, load_policy,
    pause_line, resume_line, line_status,
    available_fixers,
)

HARNESS = Path(__file__).resolve().parent
app = FastAPI(title="Dark Factory — confidence layer")

_subs: list[queue.Queue] = []
_lock = threading.Lock()


def _broadcast(event: dict):
    with _lock:
        for q in list(_subs):
            q.put(event)


@app.get("/")
def index():
    return FileResponse(HARNESS / "static" / "index.html")


app.mount("/static", StaticFiles(directory=HARNESS / "static"), name="static")


@app.get("/api/bugs")
def list_bugs():
    return BUGS


@app.post("/api/run/{bug_id}")
def run_one(bug_id: str, fixer: str | None = None):
    bug = next((b for b in BUGS if b["id"] == bug_id), None)
    if not bug:
        return JSONResponse({"error": "unknown bug"}, status_code=404)
    _broadcast({"bug_id": bug_id, "stage": "start", "status": "running",
                "detail": f"fixer={fixer or 'offline'}", "fixer": fixer or "offline"})
    threading.Thread(target=run_pipeline, args=(bug, _broadcast, fixer), daemon=True).start()
    return {"ok": True, "fixer": fixer or "offline"}


@app.post("/api/run_all")
def run_all(fixer: str | None = None):
    def go():
        for b in BUGS:
            _broadcast({"bug_id": b["id"], "stage": "start", "status": "running",
                        "detail": f"fixer={fixer or 'offline'}", "fixer": fixer or "offline"})
            run_pipeline(b, _broadcast, fixer)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True, "fixer": fixer or "offline"}


@app.get("/api/fixers")
def api_fixers():
    return available_fixers()


@app.post("/api/pause")
def pause(reason: str = "operator pause"):
    pause_line(reason)
    _broadcast({"stage": "line", "status": "paused", "bug_id": "*", "detail": reason})
    return line_status()


@app.post("/api/resume")
def resume():
    resume_line()
    _broadcast({"stage": "line", "status": "running", "bug_id": "*", "detail": "line resumed"})
    return line_status()


@app.get("/api/line")
def line():
    return line_status()


@app.get("/api/audit")
def audit():
    if not AUDIT.exists():
        return []
    return [json.loads(l) for l in AUDIT.read_text().splitlines() if l.strip()]


@app.get("/api/audit/verify")
def audit_verify():
    return verify_audit()


@app.get("/api/audit/replay/{bug_id}")
def audit_replay(bug_id: str):
    return replay(bug_id)


@app.get("/api/escalations")
def escalations():
    if not ESCALATIONS.exists():
        return []
    out = []
    for f in sorted(ESCALATIONS.glob("*.json")):
        out.append({"file": f.name, **json.loads(f.read_text())})
    return out


@app.get("/api/metrics")
def api_metrics():
    return metrics()


@app.get("/api/policy")
def api_policy():
    return load_policy()


@app.post("/api/reset")
def reset():
    if AUDIT.exists():
        AUDIT.unlink()
    if ESCALATIONS.exists():
        for f in ESCALATIONS.glob("*.json"):
            f.unlink()
    _broadcast({"stage": "reset", "status": "reset", "bug_id": "*", "detail": "fresh line"})
    return {"ok": True}


@app.get("/api/stream")
async def stream():
    q: queue.Queue = queue.Queue()
    with _lock:
        _subs.append(q)

    async def gen():
        try:
            while True:
                try:
                    item = await asyncio.get_event_loop().run_in_executor(None, q.get, True, 15)
                except queue.Empty:
                    yield ": ping\n\n"
                    continue
                yield f"data: {json.dumps(item, default=str)}\n\n"
        finally:
            with _lock:
                if q in _subs:
                    _subs.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream")
