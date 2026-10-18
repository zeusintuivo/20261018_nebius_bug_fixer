"""FastAPI server: SSE stream per pipeline run + static UI."""
from __future__ import annotations
import asyncio, json, queue, threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pipeline import run_pipeline, BUGS, AUDIT, ESCALATIONS

HARNESS = Path(__file__).resolve().parent
app = FastAPI()

# one broadcast queue per browser connection
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
def run_one(bug_id: str):
    bug = next((b for b in BUGS if b["id"] == bug_id), None)
    if not bug:
        return JSONResponse({"error": "unknown bug"}, status_code=404)
    _broadcast({"bug_id": bug_id, "stage": "start", "status": "running", "detail": ""})
    threading.Thread(target=run_pipeline, args=(bug, _broadcast), daemon=True).start()
    return {"ok": True}


@app.post("/api/run_all")
def run_all():
    def go():
        for b in BUGS:
            _broadcast({"bug_id": b["id"], "stage": "start", "status": "running", "detail": ""})
            run_pipeline(b, _broadcast)
    threading.Thread(target=go, daemon=True).start()
    return {"ok": True}


@app.get("/api/audit")
def audit():
    if not AUDIT.exists():
        return []
    return [json.loads(l) for l in AUDIT.read_text().splitlines() if l.strip()]


@app.get("/api/escalations")
def escalations():
    if not ESCALATIONS.exists():
        return []
    out = []
    for f in sorted(ESCALATIONS.glob("*.json")):
        out.append({"file": f.name, **json.loads(f.read_text())})
    return out


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
