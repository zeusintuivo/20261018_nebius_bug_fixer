# BugSmasher — Frontend Design

Audience: hackathon judges watching a 3-minute live demo.
Goal: make the *interlocks* visible. The LLM fixer is a black box; the UI is the dark-factory control room around it.

Backend is done. Everything below consumes the HTTP + SSE surface already shipped
in `harness/server.py`. No backend changes required.

---

## 1. The one-sentence story the UI must tell

> "A trivial bug walks in, three interlocks clear it, it ships itself. A nasty
> bug walks in, an interlock refuses it, a human gets paged. Everything is on
> the record and signed."

The screen has to communicate that without narration.

---

## 2. Layout — single page, four zones

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  BugSmasher  —  Dark Factory for Trivial Bugs      [Fixer: Nebius/Qwen ▾]   │  (top bar)
│  Line: ● RUNNING   Shipped 4  Escalated 1  Chain: cf5999f9…  ✓ VERIFIED      │
├────────────────┬───────────────────────────────────────────┬────────────────┤
│                │                                           │                │
│  BUG INBOX     │           FACTORY LINE                    │  AUDIT LEDGER  │
│  (left rail)   │           (center, the hero)              │  (right rail)  │
│                │                                           │                │
│  ○ BUG_A       │   ┌─ BUG_A ──────────────────────────┐    │  #36  shipped  │
│  ○ BUG_B       │   │ ① ② ③ ④ ⑤ ⑥  ✅ shipped          │    │  #35  deploy   │
│  ○ BUG_C       │   └──────────────────────────────────┘    │  #34  diff     │
│  ● BUG_D       │                                           │  #33  oracle   │
│  ○ BUG_E       │   ┌─ BUG_D ──────────────────────────┐    │  #32  bbox     │
│                │   │ ① ② ⛔                           │    │  …             │
│  [Run all]     │   │   refused: NOT_TRIVIAL           │    │  ↳ click row:  │
│  [Reset]       │   └──────────────────────────────────┘    │     replay     │
│                │                                           │                │
│                ├───────────────────────────────────────────┤                │
│                │  ESCALATION INBOX (bottom center drawer)  │                │
│                │  BUG_D — NOT_TRIVIAL — reason, raw LLM …  │                │
└────────────────┴───────────────────────────────────────────┴────────────────┘
```

### Top bar
- Product name + tagline.
- **Fixer selector** (dropdown, from `/api/fixers`). Shows readiness dot per fixer.
  This is the "the arm is swappable" moment.
- Line health strip: `RUNNING | PAUSED`, counters from `/api/metrics`, audit
  head hash + `✓ VERIFIED` badge (polls `/api/audit/verify` every 10 s; turns
  red if `ok:false`).
- **Pause / Resume** button (operator "on the loop" — PDF quote).

### Left rail — Bug inbox
- Cards from `/api/bugs`. Each shows `id`, `file`, `symptom`.
- Dot color = latest state received over SSE for that bug.
- Click a card = run that bug via `POST /api/run/{id}?fixer=…`.
- `Run all` and `Reset` buttons.

### Center — Factory line (the hero)
One **swimlane per bug** that's been run. Each lane is a horizontal row of six
**stage pills** matching the pipeline:

| # | Stage       | Pill label  | Green means                            | Red means          |
|---|-------------|-------------|----------------------------------------|--------------------|
| 1 | `qualify`   | QUALIFY     | in trivial allowlist, repro possible   | NOT_TRIVIAL        |
| 2 | `blackbox`  | FIXER       | patch returned                         | NO_PATCH           |
| 3 | `oracle`    | ORACLE      | red→green + regression green            | TEST_FAIL          |
| 4 | `diff`      | DIFF        | ≤N lines, no protected, no banned imp. | PROTECTED_PATH …   |
| 5 | `deploy`    | DEPLOY      | canary SLO ok                          | SLO_BREACH         |
| 6 | `shipped` / `escalated` | SHIP | fix in production                      | human paged        |

Pill states: `pending` (grey), `running` (amber, pulsing), `pass` (green),
`fail` (red), `blocked` (dark grey).

Pills animate in real time off `/api/stream` SSE events
(`{bug_id, stage, status, detail, code?, fixer}`).

Clicking a pill opens a side drawer with:
- the full `detail` text,
- the structured reason `code`,
- for `blackbox`: the fixer name + raw LLM response if available (from
  escalation record — this is the "replay any decision" moment),
- for `diff`: the actual patch rendered with syntax highlighting,
- a `Copy audit entry` button.

**Visual metaphor:** the swimlane literally looks like a conveyor belt. Pills
are the stations. A red pill is a stop light. The "refusal" is visibly a
physical interlock dropping, not an error dialog.

### Right rail — Audit ledger
- Append-only list from `/api/audit`, newest on top.
- Each row: `#seq  stage  status  bug_id  short-hash`.
- Click a row → "Replay this decision" modal showing the full chain for that
  `bug_id` (uses `/api/audit/replay/{bug_id}`), rendered as a timeline.
- Footer: head hash + `✓ Chain verified` / `✗ TAMPERED at #N` from
  `/api/audit/verify`. Red state must be visually alarming.
- **Demo-only button**: `Tamper (demo)` that corrupts one line in the audit log
  on the server (we can add a `POST /api/debug/tamper` behind a flag) so a
  judge can watch the chain alarm trip. Optional but a crowd-pleaser.

### Bottom center — Escalation inbox
- Drawer that slides up when `/api/escalations` is non-empty.
- Each item: `bug_id`, reason `code`, human-readable reason, fixer used, time.
- Expandable to show the full escalation JSON (includes raw LLM output when
  the fixer was an LLM — this is a differentiator: "we don't just say no, we
  show you what the arm tried to do").

---

## 3. Data flow

```
    ┌──────────┐   fetch     ┌────────────────────┐
    │ Browser  │ ─────────▶ │  /api/bugs         │  on load
    │          │ ─────────▶ │  /api/fixers       │  on load
    │          │ ─────────▶ │  /api/policy       │  on load  → "Policy" tab
    │          │ ─────────▶ │  /api/metrics      │  poll every 2 s
    │          │ ─────────▶ │  /api/audit/verify │  poll every 10 s
    │          │                                   │
    │          │   SSE      │  /api/stream       │  always open
    │          │ ◀───────── │                    │
    │          │                                   │
    │          │   POST     │  /api/run/{id}     │  on card click
    │          │   POST     │  /api/pause        │  on pause button
    │          │   POST     │  /api/reset        │  on reset
    └──────────┘            └────────────────────┘
```

Keep a client-side `Map<bug_id, Lane>` keyed by `bug_id`. Each SSE event mutates
the matching lane's stage array. Rendering is a straight projection of that
state.

---

## 4. Visual language

- **Palette:** industrial. Charcoal background `#0f1115`, panels `#161a21`,
  text `#d8dee9`. Pills: pending `#2a2f38`, running `#f5a524` (amber, pulse),
  pass `#19c37d` (green), fail `#ff5c5c` (red), blocked `#4a4e58`.
- **Type:** one monospace for IDs / hashes / diffs (JetBrains Mono),
  one geometric sans (Inter) for everything else.
- **Motion:** restrained. Only two animations:
  1. Amber pulse on `running` pills (0.8 s ease-in-out, infinite).
  2. Lane shimmer when a bug finishes, 400 ms, then settle.
- **No gradients, no shadows, no rounded avatars.** This is a factory, not a
  SaaS dashboard. The look should feel closer to a Grafana / SCADA panel than
  to a marketing site. That restraint is itself a design statement for the
  "dark factory" theme.
- **One hero color per outcome.** Green = shipped, red = escalated. Judges
  should be able to tell outcomes from across the room.

---

## 5. Hierarchy for the live demo

The eye should hit, in order:
1. The **line health strip** (am I running? is the chain intact?).
2. The **swimlanes** flowing left-to-right as bugs run.
3. The **red pill** on BUG_D when it drops. This is the money shot.
4. The **escalation drawer** sliding up with the human-readable reason.
5. The **audit chain hash** ticking forward with every event.

Everything else is secondary and should visually recede.

---

## 6. Implementation notes (zero-build path)

- Single `harness/static/index.html` + `app.js` + `style.css`. Already mounted
  by `server.py` at `/`.
- Vanilla JS. No framework. The whole state model fits in ~150 lines.
- SSE via native `EventSource`.
- Use CSS grid for the four zones, flex for swimlanes.
- Optional stretch: swap vanilla for Preact (10 kB) if we want a cleaner render
  loop — but not required.

Rough file budget:
```
harness/static/
  index.html      ~120 lines  (shell + zones)
  app.js          ~250 lines  (SSE + state + render)
  style.css       ~200 lines  (palette + swimlane + pills)
```

---

## 7. What we deliberately do NOT build

- No login / multi-user. Single operator.
- No historical charts. Metrics are a strip, not a dashboard.
- No settings page. Policy is read-only from `/api/policy` and rendered as
  JSON in a collapsible panel ("the interlocks are configuration").
- No dark/light toggle. Dark only. It's a dark factory.
- No fancy diff viewer library. `<pre>` with +/- line prefixes is enough.

---

## 8. Winning moments the UI must stage

These are the three screenshots that go in the pitch deck:

1. **Four green lanes.** BUG_A, BUG_B, BUG_C, BUG_E all shipped under Nebius.
   Audit chain shows 24+ signed entries. No human touched anything.
2. **One red stop.** BUG_D's QUALIFY pill red, lane halts, escalation drawer
   open with reason `NOT_TRIVIAL` and the raw bug report. Operator sees it
   immediately.
3. **Tamper alarm.** Someone edits `audit.log`. The `✓ VERIFIED` badge in the
   top bar flips to `✗ TAMPERED at #N`. The whole top strip turns red.
   (This is why the chain is signed, not just hashed.)

If the judges remember any one thing, it should be #2.

---

## 9. Backend endpoints the frontend will touch (reference)

Already live, verified this session:

```
GET  /api/bugs                   → 5 seeded bugs with symptom text
GET  /api/fixers                 → [{name, ready, note}]  offline/nebius/gemini
GET  /api/policy                 → interlock config as JSON
GET  /api/metrics                → {auto_shipped, escalated, by_code, throughput}
GET  /api/line                   → {paused, paused_reason}
GET  /api/audit                  → full signed, hash-chained ledger
GET  /api/audit/verify           → {ok, entries, head} or {ok:false, bad_line}
GET  /api/audit/replay/{bug_id}  → ordered decision trail for one bug
GET  /api/escalations            → human-handoff inbox
GET  /api/stream                 → SSE: {bug_id, stage, status, detail, code?, fixer}
POST /api/run/{bug_id}?fixer=…   → kick one bug
POST /api/run_all?fixer=…        → kick all five
POST /api/pause ?reason=…        → operator stops the line
POST /api/resume                 → operator resumes
POST /api/reset                  → wipe audit + escalations
```

SSE event shape (what every lane consumes):

```json
{
  "bug_id": "BUG_A",
  "stage":  "oracle",
  "status": "pass",         // running | pass | fail | blocked | shipped | escalated
  "code":   null,           // structured reason when fail/blocked
  "detail": "repro red→green, 7 regression tests green",
  "fixer":  "nebius"
}
```
