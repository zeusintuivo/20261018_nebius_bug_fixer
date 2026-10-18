"""The confidence layer. Pre-checks → black box → post-checks → gated deploy → audit.

Everything that gives the dark factory its trust lives in this file:
  * policy loader (interlocks are DATA, not code)
  * HMAC-signed, hash-chained audit log (tamper-evident, verifiable)
  * structured reason codes on every stage decision
  * pause / resume (human on-the-loop)
  * SLO-aware canary deploy with auto-rollback
"""
from __future__ import annotations
import hashlib, hmac, json, os, random, re, shutil, subprocess, sys, threading, time, uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# Load .env BEFORE importing fixers so API keys are visible to them.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

from fixer import get_patch, available as available_fixers  # noqa: E402

HARNESS = Path(__file__).resolve().parent
REPO = HARNESS.parent / "sample_repo"
SCRATCH = HARNESS / "_scratch"
DEPLOYED = HARNESS / "deployed"
AUDIT = HARNESS / "audit" / "audit.log"
ESCALATIONS = HARNESS / "escalations"
POLICY_FILE = HARNESS / "policy.json"


# ---------- policy (hot-reloaded on every run) ----------

def load_policy() -> dict:
    return json.loads(POLICY_FILE.read_text())


# ---------- reason codes (used by UI to color + group) ----------

class Code:
    OK                      = "OK"
    NOT_TRIVIAL             = "NOT_TRIVIAL"
    NO_PATCH                = "NO_PATCH"
    REPRO_NOT_FIXED         = "REPRO_NOT_FIXED"
    REGRESSION              = "REGRESSION"
    PROTECTED_PATH          = "PROTECTED_PATH"
    BANNED_IMPORT           = "BANNED_IMPORT"
    SECRET_LITERAL          = "SECRET_LITERAL"
    PATCH_TOO_LARGE         = "PATCH_TOO_LARGE"
    CANARY_SLO_BREACH       = "CANARY_SLO_BREACH"
    PAUSED                  = "PAUSED"


# ---------- line control (human on-the-loop) ----------

_line_state = {"paused": False, "paused_reason": ""}

def pause_line(reason: str = "operator pause"):
    _line_state["paused"] = True
    _line_state["paused_reason"] = reason

def resume_line():
    _line_state["paused"] = False
    _line_state["paused_reason"] = ""

def line_status() -> dict:
    return dict(_line_state)


# ---------- reproducing tests the harness can auto-generate ----------
# (In a real impl these come from the bug report's reproduction script.
#  For the demo they're pre-baked, keyed by bug id.)

REPRO_TESTS = {
    "BUG_A": ("test_calculator.py", "def test_repro_bug_a():\n    from calculator import sum_range\n    assert sum_range(5) == 15\n"),
    "BUG_B": ("test_calculator.py", "def test_repro_bug_b():\n    from calculator import is_even\n    assert is_even(4) is True\n"),
    "BUG_C": ("test_calculator.py", "def test_repro_bug_c():\n    from calculator import safe_len\n    assert safe_len(None) == 0\n"),
    "BUG_E": ("test_calculator.py", "def test_repro_bug_e():\n    from calculator import sum_range\n    assert sum_range(0) == 0\n"),
}


@dataclass
class StageResult:
    name: str
    status: str          # "pass" | "fail" | "skip"
    code: str = Code.OK  # machine-readable reason
    detail: str = ""     # human sentence
    data: dict = field(default_factory=dict)


# ---------- audit (hash-chained + HMAC-signed) ----------

def _audit_secret() -> bytes:
    p = load_policy()["audit"]
    return os.environ.get(p["hmac_secret_env"], p["hmac_secret_default"]).encode()


def _last_hash() -> str:
    if not AUDIT.exists():
        return "GENESIS"
    last = ""
    for line in AUDIT.read_text().splitlines():
        if line.strip():
            last = line
    if not last:
        return "GENESIS"
    return json.loads(last)["hash"]


def audit_append(bug_id: str, event: str, payload: dict) -> dict:
    AUDIT.parent.mkdir(parents=True, exist_ok=True)
    prev = _last_hash()
    body = {
        "ts": time.time(),
        "bug_id": bug_id,
        "event": event,
        "payload": payload,
        "prev": prev,
    }
    canon = json.dumps(body, sort_keys=True, default=str)
    body["hash"] = hashlib.sha256((prev + canon).encode()).hexdigest()[:16]
    body["sig"] = hmac.new(_audit_secret(),
                           (body["hash"] + canon).encode(),
                           hashlib.sha256).hexdigest()[:24]
    with AUDIT.open("a") as f:
        f.write(json.dumps(body, default=str) + "\n")
    return body


def verify_audit() -> dict:
    """Walk the whole chain. Confirm every link + every signature.
    Returns {ok, entries, first_bad_line, reason}."""
    if not AUDIT.exists():
        return {"ok": True, "entries": 0, "note": "empty"}
    prev = "GENESIS"
    secret = _audit_secret()
    for i, raw in enumerate(AUDIT.read_text().splitlines(), start=1):
        if not raw.strip():
            continue
        rec = json.loads(raw)
        sig = rec.pop("sig", None)
        h = rec.pop("hash", None)
        canon = json.dumps(rec, sort_keys=True, default=str)
        expect_h = hashlib.sha256((prev + canon).encode()).hexdigest()[:16]
        if h != expect_h:
            return {"ok": False, "first_bad_line": i, "reason": "hash chain broken"}
        expect_sig = hmac.new(secret, (h + canon).encode(), hashlib.sha256).hexdigest()[:24]
        if sig != expect_sig:
            return {"ok": False, "first_bad_line": i, "reason": "signature mismatch"}
        if rec["prev"] != prev:
            return {"ok": False, "first_bad_line": i, "reason": "prev pointer mismatch"}
        prev = h
    return {"ok": True, "entries": i, "head": prev}


def replay(bug_id: str) -> list:
    """Return every audit record for one bug, in order. 'Replay any decision.'"""
    if not AUDIT.exists():
        return []
    out = []
    for line in AUDIT.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("bug_id") == bug_id:
            out.append(rec)
    return out


# ---------- stages ----------

def stage_intake(bug) -> StageResult:
    return StageResult("intake", "pass", Code.OK,
                       f"received {bug['id']}: {bug['title']}")


def stage_qualify(bug, policy) -> StageResult:
    bid = bug["id"]
    if bid not in policy["trivial_allowlist"]:
        return StageResult(
            "qualify", "fail", Code.NOT_TRIVIAL,
            "not in trivial allowlist — no auto-generable reproducing test; "
            "spec is ambiguous. Escalating to a human.",
        )
    return StageResult("qualify", "pass", Code.OK,
                       f"{bid} matches a trivial shape; reproducing test available")


def stage_blackbox(bug, fixer_name: Optional[str] = None) -> StageResult:
    from fixers import get as _get_fixer
    engine = _get_fixer(fixer_name)
    patch = get_patch(bug, fixer=fixer_name)
    debug = {
        "fixer": fixer_name or "offline",
        "raw": getattr(engine, "last_raw", "")[:4000],
        "error": getattr(engine, "last_error", ""),
    }
    if patch is None:
        return StageResult("blackbox", "fail", Code.NO_PATCH,
                           f"fixer '{fixer_name or 'offline'}' returned no patch",
                           debug)
    return StageResult(
        "blackbox", "pass", Code.OK,
        f"fixer '{fixer_name or 'offline'}' returned patch touching {len(patch)} file(s)",
        {"files": list(patch.keys()), "patch": patch, **debug},
    )


def _prepare_scratch(patch: dict) -> Path:
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    shutil.copytree(REPO, SCRATCH)
    for rel, contents in patch.items():
        p = SCRATCH / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)
    return SCRATCH


def _inject_repro(bug_id: str, scratch: Path):
    if bug_id in REPRO_TESTS:
        rel, body = REPRO_TESTS[bug_id]
        tf = scratch / "tests" / rel
        tf.write_text(tf.read_text() + "\n" + body)


def _run_pytest(cwd: Path, extra_args: list[str] | None = None) -> tuple[bool, str, dict]:
    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cwd)
        args = [sys.executable, "-m", "pytest", "-v", "--rootdir", str(cwd), "tests"]
        if extra_args:
            args += extra_args
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30, env=env)
        out = (r.stdout + r.stderr)
        result_map = {}
        for line in out.splitlines():
            m = re.match(r"(tests/\S+::\S+)\s+(PASSED|FAILED|ERROR)", line)
            if m:
                result_map[m.group(1)] = m.group(2).lower()
        return r.returncode == 0, out[-2000:], result_map
    except Exception as e:
        return False, f"pytest crashed: {e}", {}


_BASELINE: Optional[dict] = None

def _baseline_results() -> dict:
    """Which tests pass on the un-patched repo? Cached once per process."""
    global _BASELINE
    if _BASELINE is not None:
        return _BASELINE
    scratch = HARNESS / "_baseline"
    if scratch.exists():
        shutil.rmtree(scratch)
    shutil.copytree(REPO, scratch)
    _, _, rmap = _run_pytest(scratch)
    _BASELINE = rmap
    return rmap


def stage_oracle(bug, patch) -> StageResult:
    """Oracle has two obligations (straight from the brief):
       1. the reproducing test flips red→green  (the bug IS gone)
       2. tests that were green on baseline stay green  (nothing else broke)
    """
    baseline = _baseline_results()
    scratch = _prepare_scratch(patch)
    _inject_repro(bug["id"], scratch)
    _, out, rmap = _run_pytest(scratch)

    repro_id = next((k for k in rmap if k.endswith(f"test_repro_{bug['id'].lower()}")), None)
    repro_ok = repro_id is not None and rmap.get(repro_id) == "passed"
    regressions = [n for n, s in rmap.items()
                   if baseline.get(n) == "passed" and s != "passed"]

    if not repro_ok:
        return StageResult("oracle", "fail", Code.REPRO_NOT_FIXED,
                           "reproducing test did not go red→green",
                           {"pytest_tail": out[-800:]})
    if regressions:
        return StageResult("oracle", "fail", Code.REGRESSION,
                           f"regressions introduced: {', '.join(regressions)}",
                           {"regressions": regressions, "pytest_tail": out[-800:]})
    return StageResult("oracle", "pass", Code.OK,
                       "repro flipped red→green, no regressions",
                       {"repro": repro_id, "pytest_tail": out[-400:]})


def _diff_lines(patch: dict) -> int:
    total = 0
    for rel, new in patch.items():
        old = (REPO / rel).read_text() if (REPO / rel).exists() else ""
        total += abs(len(new.splitlines()) - len(old.splitlines())) + sum(
            1 for a, b in zip(new.splitlines(), old.splitlines()) if a != b
        )
    return total


def stage_diff_inspect(bug, patch, policy) -> StageResult:
    findings = []
    codes = []
    for rel in patch:
        for prot in policy["protected_paths"]:
            if rel.startswith(prot):
                findings.append(f"touches protected path: {rel}")
                codes.append(Code.PROTECTED_PATH)
    for rel, new in patch.items():
        for mod in policy["banned_imports"]:
            if re.search(rf"^\s*import\s+{mod}\b", new, re.M) or \
               re.search(rf"^\s*from\s+{mod}\b", new, re.M):
                findings.append(f"banned import '{mod}' in {rel}")
                codes.append(Code.BANNED_IMPORT)
        for pat in policy["secret_patterns"]:
            if re.search(pat, new):
                findings.append(f"possible secret literal in {rel}")
                codes.append(Code.SECRET_LITERAL)
    size = _diff_lines(patch)
    if size > policy["max_patch_line_deltas"]:
        findings.append(f"patch too large: {size} line-deltas > {policy['max_patch_line_deltas']}")
        codes.append(Code.PATCH_TOO_LARGE)

    if findings:
        return StageResult("diff_inspect", "fail", codes[0],
                           "; ".join(findings),
                           {"size": size, "findings": findings, "codes": codes})
    return StageResult("diff_inspect", "pass", Code.OK,
                       f"clean, {size} line-deltas", {"size": size})


def stage_deploy(bug, patch, policy) -> StageResult:
    """Gated deploy. Behind a flag and a 'canary'. If any SLO slips, auto-rollback."""
    if DEPLOYED.exists():
        shutil.rmtree(DEPLOYED)
    shutil.copytree(REPO, DEPLOYED)
    for rel, contents in patch.items():
        p = DEPLOYED / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(contents)
    _inject_repro(bug["id"], DEPLOYED)
    _, out, rmap = _run_pytest(DEPLOYED)
    baseline = _baseline_results()
    repro_id = next((k for k in rmap if k.endswith(f"test_repro_{bug['id'].lower()}")), None)
    regressions = [n for n, s in rmap.items() if baseline.get(n) == "passed" and s != "passed"]

    # synthetic SLO probe — in prod this reads error rate from the service
    simulated_error_rate = 0.0
    ok = (repro_id and rmap.get(repro_id) == "passed"
          and not regressions
          and simulated_error_rate <= policy["deploy"]["canary_slo_error_rate"])

    if not ok:
        # auto-rollback — the worst case stays small and undoes itself
        shutil.rmtree(DEPLOYED)
        shutil.copytree(REPO, DEPLOYED)
        return StageResult("deploy", "fail", Code.CANARY_SLO_BREACH,
                           "canary failed — auto-rolled back", {"pytest_tail": out})
    return StageResult("deploy", "pass", Code.OK,
                       "canary green, flag flipped",
                       {"flag": f"{policy['deploy']['flag_prefix']}{bug['id'].lower()}",
                        "slo_error_rate": simulated_error_rate})


def escalate(bug, reason: str, code: str, trace: list) -> str:
    ESCALATIONS.mkdir(parents=True, exist_ok=True)
    f = ESCALATIONS / f"{bug['id']}_{uuid.uuid4().hex[:6]}.json"
    f.write_text(json.dumps({
        "bug": bug, "reason": reason, "code": code,
        "trace": trace, "ts": time.time(),
    }, indent=2, default=str))
    return f.name


# ---------- orchestrator ----------

def run_pipeline(bug, emit: Callable[[dict], None], fixer_name: Optional[str] = None):
    policy = load_policy()
    fixer_name = fixer_name or os.environ.get("DARKFACTORY_FIXER") or "offline"
    trace: list[dict] = []
    audit_append(bug["id"], "run_start", {"fixer": fixer_name, "policy_version": policy.get("version")})

    def push(stage: StageResult):
        rec = {"bug_id": bug["id"], "stage": stage.name,
               "status": stage.status, "code": stage.code,
               "detail": stage.detail, "data": stage.data,
               "fixer": fixer_name}
        trace.append(rec)
        audit_append(bug["id"], f"stage:{stage.name}",
                     {"status": stage.status, "code": stage.code,
                      "detail": stage.detail, "fixer": fixer_name})
        emit(rec)
        time.sleep(0.35)  # dramatic pacing for the demo

    def check_pause():
        while _line_state["paused"]:
            emit({"bug_id": bug["id"], "stage": "paused", "status": "paused",
                  "code": Code.PAUSED, "detail": _line_state["paused_reason"]})
            time.sleep(0.5)

    def fail_and_escalate(stage: StageResult):
        name = escalate(bug, stage.detail, stage.code, trace)
        emit({"bug_id": bug["id"], "stage": "escalate", "status": "escalated",
              "code": stage.code,
              "detail": f"handed to human → {name}"})
        audit_append(bug["id"], "escalated",
                     {"reason": stage.detail, "code": stage.code, "file": name})

    check_pause(); push(stage_intake(bug))

    check_pause()
    q = stage_qualify(bug, policy); push(q)
    if q.status != "pass":
        return fail_and_escalate(q)

    check_pause()
    b = stage_blackbox(bug, fixer_name); push(b)
    if b.status != "pass":
        return fail_and_escalate(b)
    patch = b.data["patch"]

    check_pause()
    o = stage_oracle(bug, patch); push(o)
    if o.status != "pass":
        return fail_and_escalate(o)

    check_pause()
    d = stage_diff_inspect(bug, patch, policy); push(d)
    if d.status != "pass":
        return fail_and_escalate(d)

    check_pause()
    dep = stage_deploy(bug, patch, policy); push(dep)
    if dep.status != "pass":
        return fail_and_escalate(dep)

    emit({"bug_id": bug["id"], "stage": "shipped", "status": "shipped",
          "code": Code.OK,
          "detail": f"fix for {bug['id']} is live"})
    audit_append(bug["id"], "shipped", {"flag": dep.data.get("flag")})


# ---------- metrics (line health at a glance) ----------

def metrics() -> dict:
    if not AUDIT.exists():
        return {"auto_shipped": 0, "escalated": 0, "by_code": {}, "throughput": 0}
    shipped = 0
    escalated = 0
    by_code: dict[str, int] = {}
    for line in AUDIT.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec["event"] == "shipped":
            shipped += 1
        elif rec["event"] == "escalated":
            escalated += 1
            c = rec["payload"].get("code", "UNKNOWN")
            by_code[c] = by_code.get(c, 0) + 1
    return {
        "auto_shipped": shipped,
        "escalated": escalated,
        "by_code": by_code,
        "throughput": shipped + escalated,
    }


BUGS = [
    {"id": "BUG_A", "title": "sum_range off-by-one",
     "file": "calculator.py", "severity": "trivial",
     "symptom": "sum_range(5) returns 10 but should return 15 (inclusive 1..n)."},
    {"id": "BUG_B", "title": "is_even wrong operator",
     "file": "calculator.py", "severity": "trivial",
     "symptom": "is_even(4) returns False; the modulo comparison is inverted."},
    {"id": "BUG_C", "title": "safe_len crashes on None",
     "file": "calculator.py", "severity": "trivial",
     "symptom": "safe_len(None) raises TypeError; should return 0."},
    {"id": "BUG_E", "title": "sum_range(0) edge case",
     "file": "calculator.py", "severity": "trivial-looking",
     "symptom": "sum_range(0) raises instead of returning 0. ONLY touch calculator.py."},
    {"id": "BUG_D", "title": "discount_price wrong for simple percentages",
     "file": "calculator.py", "severity": "nasty",
     "symptom": "discount_price(100,10) does not return 90.00; semantics around negative/>100 percent unspecified."},
]
