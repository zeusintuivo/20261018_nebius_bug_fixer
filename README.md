# 20261018_nebius_bug_fixer
BugSmasher: Autonomous Confidence Layer for Dark Factory Bug Resolution


# BugSmasher 🛠️

> **Autonomous Confidence Layer for Dark Factory Bug Resolution**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![UI Guidelines](https://img.shields.io/badge/Design-SAP%20Fiori%203.0-0a6ed1.svg)](https://experience.sap.com/fiori-design/)
[![Code Style](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**BugSmasher** is a rigorous safety and governance confidence layer designed to let repositories fix trivial bugs autonomously and ship them directly to production without human bottlenecks.

Moving beyond simple LLM code generation, BugSmasher establishes an industrial "dark factory" pipeline featuring pre-qualification checks, automated test oracles, static diff security gates, and canary SLO rollouts. Built with modular interlocks, SHA-256 signed immutable audit ledgers, and strict out-of-the-loop governance, it ensures absolute trust backed by an enterprise-grade dashboard adhering strictly to SAP Fiori visual design guidelines.

---

## 🏛️ Core Architectural Pillars

```
+-----------------------------------------------------------------------------------+
|                                 BUGSMAHER PIPELINE                                |
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

* **Dark Factory Automation**: Zero-human-in-the-loop remediation for low-risk, verified issues.
* **Cryptographic Provenance**: SHA-256 signed immutable audit trail for full compliance and governance.
* **Deterministic Safety**: Multi-stage evaluation interlocks prevent code regression and unintended side effects.
* **SAP Fiori Enterprise UI**: Complete operational visibility adhering to enterprise SAP Fiori UX principles.

---

## 📋 Prerequisites

Before installing BugSmasher, ensure your system meets the following requirements:

* **OS**: Linux, macOS, or Windows (WSL2 recommended)
* **Python**: `3.10` or higher (the installer auto-selects `python3.10`–`python3.14`)
* **Git**: `2.30+` installed and available in `PATH`
* **Shell**: `bash` 4+ (ships with Linux, macOS, and WSL2)

The installer provisions its own virtualenv in `.venv/` — you do not need `conda`.

---

## 🚀 Installation & Setup

### 1. Clone the Repository

```bash
git clone https://github.com/your-org/bugsmasher.git
cd bugsmasher
```

### 2. Run the installer

```bash
bash install.bash
```

`install.bash` is idempotent and fails fast:

1. Picks the newest Python ≥ 3.10 on your `PATH`.
2. Creates `.venv/` in the repo root (reuses it on subsequent runs).
3. Upgrades `pip`, `setuptools`, `wheel`.
4. Installs required deps: `fastapi`, `uvicorn`, `python-dotenv`, `pytest`, `httpx`.
5. Installs optional LLM backends: `openai` (for Nebius), `google-genai` (for Gemini).
6. Verifies every required import before exiting.

Useful flags:

```bash
bash install.bash --no-optional   # skip openai + google-genai (offline fixer only)
bash install.bash --recreate      # wipe .venv and start fresh
```

If any step fails the installer stops with a red `[install:FAIL]` line — fix the cause and re-run.

---

## ⚙️ Configuration

The LLM-backed fixers (`nebius`, `gemini`) read credentials from a `.env` at the repo root. The `offline` fixer needs no configuration.

Example `.env`:

```env
# Nebius (OpenAI-compatible endpoint)
NEBIUS_API_KEY=sk-...
NEBIUS_MODEL=Qwen/Qwen2.5-Coder-32B-Instruct

# Gemini (optional)
# GEMINI_API_KEY=...
# GEMINI_MODEL=gemini-2.0-flash
```

Missing keys do not break startup — the UI simply greys-out the unconfigured fixer via `/api/fixers`.

---

## 💻 Usage

### Launch the harness

```bash
bash run.bash                 # default: http://127.0.0.1:8099
PORT=8080 bash run.bash       # pick another port
LOG_LEVEL=info bash run.bash  # uvicorn log level
```

`run.bash` auto-runs `install.bash` the first time, then verifies the venv, checks that the port is free, and `exec`s uvicorn with `harness/server:app`.

Open `http://127.0.0.1:8099/` for the SAP Fiori dashboard.

### Key endpoints

| Endpoint                        | Purpose                                              |
|---------------------------------|------------------------------------------------------|
| `GET  /api/bugs`                | List seeded bugs                                     |
| `POST /api/run/{bug_id}`        | Run the pipeline for one bug (`?fixer=offline\|nebius\|gemini`) |
| `POST /api/run_all`             | Run every bug sequentially                           |
| `GET  /api/stream`              | SSE stream of pipeline progress                      |
| `GET  /api/audit`               | Full hash-chained + HMAC-signed audit log            |
| `GET  /api/audit/verify`        | Re-walks the chain, proves no tampering              |
| `GET  /api/audit/replay/{bug}`  | Every audit event for one bug                        |
| `GET  /api/escalations`         | Inbox of bugs handed back to a human                 |
| `POST /api/pause` / `/api/resume` | Human-on-the-loop line control                     |
| `POST /api/reset`               | Wipe audit + escalations (demo convenience)          |

### Running the test suite

```bash
.venv/bin/pytest sample_repo/tests -v
```

---

## 🔒 Security & Governance

BugSmasher is engineered with strict out-of-the-loop safety mechanisms:

1. **Static Diff Interlocks**: Rejects diffs exceeding line thresholds or modifying restricted core files (e.g., security policies, root infrastructure).
2. **Deterministic Oracles**: Requires 100% test pass rate on affected functional units.
3. **Signed Ledgers**: Every execution generates a cryptographically verifiable JSON log signed via SHA-256 to ensure complete auditability for enterprise compliance.

---

## 📄 License

Distributed under the **Apache 2.0 License**. See `LICENSE` for more information.
