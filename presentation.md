---
marp: true
theme: default
paginate: true
size: 16:9
title: "BugSmasher — Autonomous Confidence Layer for Dark-Factory Bug Resolution"
description: "Technical pitch deck wired to the real scripts in this repo."
footer: "BugSmasher · dark factory for trivial bugs"
style: |
  section { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  section.lead h1 { font-size: 2.6em; }
  code { font-size: 0.85em; }
  pre { font-size: 0.75em; line-height: 1.3; }
  .cols { display: grid; grid-template-columns: 1fr 1fr; gap: 1.2em; }
  .ok   { color: #107e3e; font-weight: 600; }
  .bad  { color: #bb0000; font-weight: 600; }
  .mut  { color: #6a6d70; }
  kbd   { background: #eaeaea; border: 1px solid #ccc; border-bottom-width: 2px;
          border-radius: 4px; padding: 1px 6px; font-family: monospace; }
---

<!-- _class: lead -->

# BugSmasher 🛠️
### Autonomous Confidence Layer for Dark-Factory Bug Resolution

**One line:** an industrial safety envelope that lets a repo fix *trivial*
bugs and ship them to prod without a human bottleneck.

<span class="mut">Live demo in this deck · every slide is backed by a real file in the repo.</span>

---

## The problem

Trivial bugs clog PR queues. Humans are the bottleneck for fixes that don't
*need* a human — off-by-ones, bad defaults, swallowed exceptions.

Our fixture — `sample_repo/calculator.py` — ships with **4 seeded bugs**
(`BUG A/B/C/D`) and a test suite that surfaces them.

```bash
$ cd sample_repo && python -m pytest -q
...
2 passed, 6 failed in 0.11s
```

<span class="bad">6 failing tests.</span> That's the toy box BugSmasher fixes
on every demo run.

---

## Why not just "an LLM"?

<div class="cols">
<div>

**Naive LLM loop**

```
prompt → patch → merge → 🤞
```

- No oracle.
- No security gate.
- No rollback.
- No audit trail.

</div>
<div>

**BugSmasher pipeline**

```
prequalify → test oracle →
security gate → canary SLO →
SHA-256 signed ledger
```

- Deterministic gates.
- Immutable receipts.
- Out-of-the-loop by design.

</div>
</div>

The LLM is **one component** inside a safety envelope — not the envelope.

---

## The pipeline (one diagram, from the README)

```
+-----------------------------------------------------------------------------------+
|                                 BUGSMASHER PIPELINE                               |
+------------------+-------------------+--------------------+-----------------------+
|  1. Prequalify   | 2. Test Oracles   | 3. Security Gates  |  4. Canary SLO        |
|  Local Diff      | Automated Suite   | Static Diff Check  |  Automated Rollout    |
+------------------+-------------------+--------------------+-----------------------+
                                       │
                                       ▼
                   ┌─────────────────────────────────────────┐
                   │ SHA-256 Immutable Audit Ledger (Signed) │
                   └─────────────────────────────────────────┘
                                       │
                                       ▼
                   ┌─────────────────────────────────────────┐
                   │   SAP Fiori Enterprise Dashboard UI     │
                   └─────────────────────────────────────────┘
```

Source: `harness/pipeline.py` + `harness/server.py` + `harness/fixers/*.py`.

---

## 🔴 LIVE DEMO — part 1: onboarding

Click the slide title, drop to the terminal, run:

```bash
bash demo.bash --fast --no-serve
```

What the audience sees (narrated by `demo.bash`):

1. The toy box — `sample_repo/calculator.py` printed in-line.
2. The 6 failing tests surface as "broken parts."
3. The three fixer helpers introduce themselves:
   `offline`, `gemini`, `nebius`.
4. The 4 safety gates read aloud.

**Betterment to call out:** one command, zero prior knowledge,
deterministic output. Non-engineers understand it on the first run.

---

## 🔴 LIVE DEMO — part 2: the server

```bash
PORT=8243 bash run.bash
```

Open the dashboard, hit the real endpoints (all live, verified in this repo):

| Endpoint                     | What it returns                 |
|------------------------------|---------------------------------|
| `GET  /api/bugs`             | the seeded bug catalogue        |
| `GET  /api/fixers`           | the fixer roster + status       |
| `GET  /api/policy`           | the active gate policy          |
| `POST /api/run/{bug_id}`     | run the pipeline on one bug     |
| `POST /api/run_all`          | run every bug end-to-end        |
| `GET  /api/audit/verify`     | re-check the SHA-256 ledger     |
| `GET  /api/stream`           | SSE live feed of pipeline steps |

**Betterment:** same binary powers CI, local dev, and the Fiori dashboard —
no second code path, no "demo-mode" fork.

---

## Tooling betterments — the meat (1/2)

### 1. `install.bash` — fail-fast installer
- Auto-picks the newest Python ≥ 3.10 on `PATH`.
- Creates `.venv`, upgrades pip/setuptools/wheel.
- Installs required deps (`fastapi`, `uvicorn`, `python-dotenv`, `pytest`, `httpx`).
- Installs optional LLM backends (`openai`, `google-genai`) — soft-fails.
- Verifies every import before exiting 0. `--recreate` wipes & rebuilds.

### 2. `run.bash` — self-healing launcher
- Bootstraps `.venv` automatically if missing.
- Verifies `harness/server.py`, imports `uvicorn` + `fastapi` before launch.
- Probes port with `lsof`, fails cleanly on conflict.
- `exec`s uvicorn so `Ctrl-C` goes straight to the server.

---

## Tooling betterments — the meat (2/2)

### 3. `demo.bash` — storytelling CLI
- Toy-box metaphor, pacing control, colour-coded steps.
- `--fast`, `--no-serve`, `--help`.
- Hands off to `run.bash` with an auto-picked free port 8099–8199.
- Non-engineers run the full flow unaided.

### 4. Adversarial + tester agent loop (meta-tooling)
Every change in this repo goes through:
1. **executor** — writes the diff.
2. **tester** — runs the narrowest pytest / shell check that covers it.
3. **adversary** — tries to break it with concrete inputs.

Proof: this very deck was built under that loop; the previous turns'
transcripts are the receipt.

---

## Governance you can point at

- **SHA-256 signed audit ledger** — every autonomous action gets an
  immutable, chained record. Verify with `GET /api/audit/verify`.
- **Static diff security gate** — rejects new network calls, `eval`,
  secret writes, writes to `protected/` paths.
- **Canary SLO rollout** — automatic rollback on error-rate regression.
- **Escalation path** — anything the gates refuse lands in
  `harness/escalations/` as a human-readable `.json` with the refusal reason.
- **Out-of-the-loop by design, not by accident** — there is no "yolo" flag.

---

## Numbers (defendable from this repo today)

- **Seeded bugs in fixture:** 4 (`BUG A/B/C/D` in `sample_repo/calculator.py`).
- **Failing tests before pipeline:** 6 / 8.
- **Audit coverage of autonomous actions:** 100% (ledgered).
- **Install → first green server:** one command, ~30 s on a fresh clone.
- **Endpoints shipped:** 16 (see `harness/server.py`).
- **Fixer backends shipped:** 3 (`offline`, `gemini`, `nebius`).

Everything else — time-to-fix vs. humans, false-positive rate, pre-qual
pass rate — <span class="mut">*not measured yet; honest "TBD"*.</span>

---

## What this *isn't*

BugSmasher does **not**:

- fix architectural bugs
- modify public APIs
- bypass code owners on protected paths (`harness/protected/`, `sample_repo/protected/`)
- run without the gates — there is no "yolo" mode
- replace human review for anything flagged by prequalify

This slide buys trust. If a prospect's bug doesn't fit the envelope,
BugSmasher escalates instead of guessing.

---

## Roadmap

<div class="cols">
<div>

**Shipped today**
- Pipeline (4 gates)
- 3 fixer backends
- 16 live endpoints
- Fiori dashboard (static)
- `install.bash` / `run.bash` / `demo.bash`
- Signed audit ledger
- Escalation sink

</div>
<div>

**Next**
- More fixer archetypes (type-hint-only, lint-only, test-only)
- Richer SLO signals (p95 latency, 5xx rate)
- GitHub App bridge (PR → pipeline)
- Nebius token-factory multi-model routing
- Per-repo policy packs

</div>
</div>

---

## The ask

Pick one — don't ask for everything:

- **Pilot repo** — one small, trusted repo for 30 days.
- **Security review slot** — 60 min with your sec team.
- **A sponsor** — one eng leader willing to green-light the pilot.

End on a concrete ask, not "thank you."

---

<!-- _class: lead -->

## Run the demo now

```bash
bash install.bash          # one-time, idempotent
bash demo.bash             # story mode + launches server
# demo.bash prints the actual URL (auto-picks a free port 8099-8199)
```

Or just the server:

```bash
PORT=8243 bash run.bash
```

<span class="mut">Everything on these slides is a file in the repo. Nothing
is slideware.</span>

---

## Appendix — presenter notes

- **12 content slides + 1 run-the-demo slide + this appendix.** ~15 min + 10 min live.
- Run the demo on a **fresh clone** on a second machine. The `install.bash`
  → `demo.bash` story only lands if they see it from zero.
- Keep a tmux pane tailing `harness/audit/audit.log` during the demo
  so ledger entries appear live.
- **Backup video** of the demo on disk in case wifi/pip dies.
- If a prospect asks "what if the LLM is wrong?" — point at slide 3 and 10.
  The gates catch it; the escalation path records it.
