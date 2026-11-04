"""Compile a candidate declaration in a prepared environment and measure
heartbeats. Putnam (self-contained) path for now: header + declaration is
written to a scratch file inside the Mathlib worktree and run with
`lake env lean --json`.

Heartbeats: Mathlib's `#count_heartbeats in` is pathologically slow on some
declarations (15+ min vs 7 s plain compile on putnam_1964_a4, Oct 6), so we
inject a tiny measuring command (`arena_measure`) that reads
`IO.getNumHeartbeats` around `elabCommand`, under `set_option Elab.async
false` so the work stays on the counting thread. Calibration on the three
PutnamBench references (newest toolchain): +0.05%, +0.07%, +0.8% vs
`benchmark_heartbeats.jsonl`. Tracked in STATUS.md.
"""
from __future__ import annotations

import json, os, re, subprocess, sys, time, uuid
from dataclasses import dataclass, field
from pathlib import Path
from scorer.memgate import run_lean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ELAN_BIN = Path.home() / ".elan/bin"
USED_RE = re.compile(r"ARENA_HB (\d+)")
MEASURE_ELAB = """open Lean Elab Command in
elab "arena_measure " cmd:command : command => do
  let t0 ← IO.getNumHeartbeats
  elabCommand cmd
  let t1 ← IO.getNumHeartbeats
  logInfo m!"ARENA_HB {(t1 - t0) / 1000}"

"""


@dataclass
class CompileResult:
    ok: bool
    heartbeats: int | None
    seconds: float
    errors: list[str] = field(default_factory=list)
    warnings: int = 0
    timed_out: bool = False
    raw: str = ""
    messages: list = field(default_factory=list)
    hb_blind: bool = False   # compiled, but arena_measure could not be defined in this file: no heartbeats (P0-5 item 4)


def env_dir(version: str, source: str = "putnambench") -> Path:
    if source == "putnambench":
        return ROOT / "envs" / f"mathlib-{version}"
    raise NotImplementedError(f"env for {source}")


def compile_putnam(header: str, declaration: str, version: str, *, count: bool = True,
                   timeout: int = 600) -> CompileResult:
    wd = env_dir(version)
    scratch = wd / "LRAScratch"
    scratch.mkdir(exist_ok=True)
    f = scratch / f"c_{uuid.uuid4().hex[:12]}.lean"
    if count:
        text = header.rstrip() + "\n\n" + MEASURE_ELAB + "set_option Elab.async false in\narena_measure\n" + declaration.rstrip() + "\n"
    else:
        text = header.rstrip() + "\n\n" + declaration.rstrip() + "\n"
    f.write_text(text)
    env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH','')}")
    t0 = time.time()
    try:
        p = run_lean(["lake", "env", "lean", "--json", f"-M{os.environ.get('LRA_LEAN_MEMORY_MB', '16000')}", str(f.relative_to(wd))], cwd=wd, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        f.unlink(missing_ok=True)
        return CompileResult(False, None, time.time() - t0, ["timeout"], timed_out=True,
                             raw=(e.stdout or b"")[:2000] if isinstance(e.stdout, bytes) else str(e.stdout)[:2000])
    secs = time.time() - t0
    f.unlink(missing_ok=True)
    errors, warnings, hb, messages = [], 0, None, []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        messages.append(m)
        sev, data = m.get("severity"), m.get("data", "")
        if sev == "error":
            errors.append(f"{m.get('pos',{}).get('line')}:{m.get('pos',{}).get('column')}: {data}")
        elif sev == "warning":
            warnings += 1
        if sev == "information":
            mm = USED_RE.search(data)
            if mm:
                hb = int(mm.group(1))
    ok = p.returncode == 0 and not errors
    if p.returncode != 0 and not errors:
        errors.append(f"lean exit {p.returncode}: {p.stderr[-500:]}")
    return CompileResult(ok, hb, secs, errors, warnings, raw=p.stdout[-4000:], messages=messages)


# ---------------------------------------------------------------------------
# Project-resident problems (Strata, CSLib, PhysLib, ArkLib): the worker
# compiles the declaration in place inside the repository at the pinned
# commit. We replicate that by writing a scratch module that contains the
# original file's prefix (everything before `start_line`) followed by the
# candidate declaration, and compiling it with `lake env lean` from the
# project root so imports resolve against the built oleans.
# ---------------------------------------------------------------------------

PROJECT_DIRS = {"strata": "strata", "cslib": "cslib", "physlib": "physlib", "arklib": "arklib"}


def project_env_dir(source: str, version: str) -> Path:
    return ROOT / "envs" / f"{PROJECT_DIRS[source]}-{version}"


def _ws_regex(text: str) -> re.Pattern:
    """Regex matching `text` with any whitespace run allowed where it has one."""
    parts = [re.escape(t) for t in text.split()]
    return re.compile(r"\s+".join(parts))


def locate(source: str, version: str, file_path: str, statement: str, src: str) -> tuple[str, int]:
    """Find the reference declaration in the file at the pinned commit and
    return (prefix_text, line_number). The benchmark's start_line/end_line are
    unreliable (the CallElimCorrect rows point at other declarations) and the
    proof text can differ by whitespace across commits (ArkLib at v4.30.0),
    so we match the *statement* with whitespace-tolerant search, preferring an
    exact match of the whole declaration when one exists."""
    text = (project_env_dir(source, version) / file_path).read_text()
    needle = src.rstrip("\n")
    i = text.find(needle)
    if i >= 0 and text.find(needle, i + 1) < 0:
        return text[:i], text[:i].count("\n") + 1
    hits = [m.start() for m in _ws_regex(statement).finditer(text)]
    # the statement must be followed by `:=` to be the declaration itself
    hits = [h for h in hits if re.match(r"\s*:=", text[_ws_regex(statement).match(text, h).end():])]
    if len(hits) != 1:
        raise ValueError(f"statement found {len(hits)} times in {file_path} @ {version}")
    return text[:hits[0]], text[:hits[0]].count("\n") + 1


def file_prefix(row: dict, version: str) -> str:
    return locate(row["source"], version, row["file_path"], row["statement"], row["src"])[0]


# Trailing modifiers that belong to the declaration: docstrings, attributes, visibility keywords and `open … in`; the measuring command
# is inserted before them. `set_option … in` / `omit … in` / `include … in` / `unseal … in` / `variable … in` are deliberately NOT in this
# list (P0-5, 2026-10-12): they stay in the core, so they attach to `arena_measure`'s elab definition and the theorem is measured
# without them (e.g. ArkLib's `omit [CharP L 2] [NeZero ℓ] in` does not remove those instance hypotheses). That is what the official
# worker measures: attaching them to the theorem moved the predicted heartbeat ratio 3x further from submit/results/*.worker.json
# (mean error 0.0016 -> 0.0052). Validity is still checked with them attached (_ATTACHED_IN below). docs/scorer_options.md.
_MODIFIER_TAIL = re.compile(
    r"((?:/--(?:(?!-/).)*-/\s*|@\[[^\]\n]*\]\s*|(?:private|protected|noncomputable|nonrec|partial|unsafe|public|meta|scoped|local|open\s+[\w.\s]+?\s+in)\s+)*)\Z",
    re.DOTALL)
# A core ending in one of these `… in` combinators gets a second, unmeasured compile in file order (the combinator applies to the
# theorem, as in `lake build`); the candidate must pass both. Linter / pretty-printer `set_option`s cannot change validity: skipped.
_ATTACHED_IN = re.compile(r"(?:^|\n)[ \t]*(?:omit|include|unseal|variable|set_option(?![ \t]+(?:weak\.)?(?:linter|pp)\.))\b[^\n]*\bin[ \t]*\n?\s*\Z")

# Lakefile options (2026-10-12, P0-5): `lake env lean` on a scratch file ignores a project's lakefile `leanOptions` / `moreLeanArgs`.
# Only options that can change what compiles or what elaboration costs are passed (as -D flags); linter, style and pretty-printer
# options only add warnings and are left out. Evidence and per-option decisions: docs/scorer_options.md.
SEMANTIC_OPTIONS = {"autoImplicit", "relaxedAutoImplicit", "warningAsError", "experimental.module", "warn.sorry", "says.verify",
                    "maxSynthPendingDepth", "maxHeartbeats", "maxRecDepth", "synthInstance.maxHeartbeats", "synthInstance.maxSize"}


def _semantic(key: str) -> bool:
    key = key.removeprefix("weak.")
    return key in SEMANTIC_OPTIONS or key.startswith("backward.")


def _fmt(v) -> str:
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def lakefile_options(source: str, version: str) -> tuple[str, ...]:
    """-D flags for the semantic options in this pin's lakefile (top-level leanOptions, every lean_lib's leanOptions and moreLeanArgs)."""
    wd = project_env_dir(source, version); flags: list[str] = []
    toml_f, lean_f = wd / "lakefile.toml", wd / "lakefile.lean"
    if toml_f.exists():
        import tomllib
        d = tomllib.loads(toml_f.read_text())
        tables = [d.get("leanOptions") or {}] + [lib.get("leanOptions") or {} for lib in d.get("lean_lib", [])]
        def flat(t, pre=""):
            for k, v in t.items():
                yield from (flat(v, f"{pre}{k}.") if isinstance(v, dict) else [(f"{pre}{k}", v)])
        for t in tables:
            flags += [f"-D{k}={_fmt(v)}" for k, v in flat(t) if _semantic(k)]
        for lib in d.get("lean_lib", []):
            flags += [a for a in lib.get("moreLeanArgs", []) if a.startswith("-D") and _semantic(a[2:].split("=")[0])]
    elif lean_f.exists():   # lakefile.lean: ⟨`key, value⟩ pairs in leanOptions / moreLeanArgs strings
        t = lean_f.read_text()
        for k, v in re.findall(r"⟨`([\w.]+),\s*(?:\.ofNat\s+|\.ofBool\s+|\.ofString\s+)?\(?([\w.\"]+)\)?\s*⟩", t):
            if _semantic(k):
                flags.append(f"-D{k}={v.strip(chr(34))}")
        flags += [a for a in re.findall(r'"(-D[\w.]+=[^"]+)"', t) if _semantic(a[2:].split("=")[0])]
    return tuple(dict.fromkeys(flags))   # de-duplicated, order kept


def split_modifiers(prefix: str) -> tuple[str, str]:
    """Split the file prefix into (core, trailing declaration modifiers).
    Docstrings and attributes immediately before the declaration belong to
    it syntactically, so the measuring command must be inserted before them."""
    m = _MODIFIER_TAIL.search(prefix)
    if not m or not m.group(1):
        return prefix, ""
    return prefix[: m.start(1)], m.group(1)


def _measure_lines(core: str) -> range:
    """Line numbers of MEASURE_ELAB (the elab definition, not the `arena_measure` call, where the declaration's own errors can land)
    in a measured body built from `core`."""
    start = core.rstrip("\n").count("\n") + 3
    return range(start, start + MEASURE_ELAB.count("\n"))


# A module file (`module` header) whose imports do not bring Lean.Elab.Command into scope cannot define arena_measure ("unknown
# namespace `Command`"); a `public meta import Lean.Elab.Command` right after the `module` line fixes it (P0-5 item 4: 7 of 7 such
# files probed at Strata v4.29.1 and v4.26.0). It is added only to files that need it, so every other file compiles exactly as before.
_MODULE_LINE = re.compile(r"\A(?:\s+|--[^\n]*\n|/-(?:(?!-/).)*-/)*module[ \t]*\n", re.DOTALL)
MEASURE_IMPORT = "public meta import Lean.Elab.Command\n"
_NEEDS_IMPORT: set = set()
_BLIND_WARNED: set = set()


def _with_measure_import(core: str) -> str | None:
    m = _MODULE_LINE.match(core)
    return core[: m.end()] + MEASURE_IMPORT + core[m.end():] if m else None


def _measure_failed(res: CompileResult, core: str) -> bool:
    span = _measure_lines(core)
    return not res.ok and any((m.get("pos") or {}).get("line") in span for m in res.messages if m.get("severity") == "error")


def compile_project(row: dict, declaration: str, version: str, *, count: bool = True,
                    timeout: int = 900, lean_args: tuple | None = None) -> CompileResult:
    """`lean_args`: extra flags for `lean`. None (default, 2026-10-12) = the pin's semantic lakefile options (lakefile_options), which
    `lake env lean` on a scratch file would otherwise ignore; () = none, as before.
    With `count`, three guards (P0-5, docs/scorer_options.md): a core ending in a validity-relevant `… in` combinator (_ATTACHED_IN)
    also gets an unmeasured compile in file order and the candidate must pass both; a module file where `arena_measure` cannot be
    defined is measured with MEASURE_IMPORT added (remembered per file and pin); and if even that fails, the result is the unmeasured
    compile with heartbeats=None and hb_blind=True, with a warning once per file and pin, instead of every candidate failing."""
    source = row["source"]
    if lean_args is None:
        lean_args = lakefile_options(source, version)
    core, modifiers = split_modifiers(file_prefix(row, version))
    if not count:
        return _lean_in_project(source, version, core.rstrip("\n") + "\n\n" + modifiers + declaration.rstrip() + "\n", lean_args, timeout)
    key = (source, version, row["file_path"])
    measured = lambda c: _lean_in_project(source, version, c.rstrip("\n") + "\n\n" + MEASURE_ELAB + "set_option Elab.async false in\n"
                                          "arena_measure\n" + modifiers + declaration.rstrip() + "\n", lean_args, timeout)
    mcore = (_with_measure_import(core) or core) if key in _NEEDS_IMPORT else core
    res = measured(mcore)
    if _measure_failed(res, mcore) and mcore is core and _with_measure_import(core):
        mcore = _with_measure_import(core)
        retry = measured(mcore)
        retry.seconds += res.seconds
        res = retry
        if not _measure_failed(res, mcore):
            _NEEDS_IMPORT.add(key)
    if _measure_failed(res, mcore):
        plain = compile_project(row, declaration, version, count=False, timeout=timeout, lean_args=lean_args)
        plain.seconds += res.seconds
        plain.hb_blind = True
        if (source, version, row["file_path"]) not in _BLIND_WARNED:
            _BLIND_WARNED.add((source, version, row["file_path"]))
            print(f"WARNING scorer.compile: arena_measure cannot be defined in this {source} @ {version} file ({res.errors[0][:120]}); "
                  "heartbeats unavailable there (hb_blind), validity from the unmeasured compile", file=sys.stderr, flush=True)
        return plain
    if res.ok and _ATTACHED_IN.search(core):
        plain = compile_project(row, declaration, version, count=False, timeout=timeout, lean_args=lean_args)
        res.seconds += plain.seconds
        if not plain.ok:
            res.ok, res.timed_out = False, plain.timed_out
            res.errors = [f"(with the preceding `… in` modifier applied to the declaration, as in the file) {e}" for e in plain.errors]
    return res


def _lean_in_project(source: str, version: str, body: str, lean_args: tuple, timeout: int) -> CompileResult:
    wd = project_env_dir(source, version)
    scratch_dir = wd / "LRAScratch"
    scratch_dir.mkdir(exist_ok=True)
    f = scratch_dir / f"c_{uuid.uuid4().hex[:12]}.lean"
    f.write_text(body)
    env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH','')}")
    t0 = time.time()
    try:
        p = run_lean(["lake", "env", "lean", "--json", f"-M{os.environ.get('LRA_LEAN_MEMORY_MB', '16000')}", *lean_args, str(f.relative_to(wd))], cwd=wd, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        f.unlink(missing_ok=True)
        return CompileResult(False, None, time.time() - t0, ["timeout"], timed_out=True)
    secs = time.time() - t0
    f.unlink(missing_ok=True)
    errors, warnings, hb, messages = [], 0, None, []
    for line in p.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            continue
        messages.append(m)
        sev, data = m.get("severity"), m.get("data", "")
        if sev == "error":
            errors.append(f"{m.get('pos',{}).get('line')}:{m.get('pos',{}).get('column')}: {data}")
        elif sev == "warning":
            warnings += 1
        if sev == "information":
            mm = USED_RE.search(data)
            if mm:
                hb = int(mm.group(1))
    ok = p.returncode == 0 and not errors
    if p.returncode != 0 and not errors:
        errors.append(f"lean exit {p.returncode}: {p.stderr[-500:]}")
    return CompileResult(ok, hb, secs, errors, warnings, raw=p.stdout[-4000:], messages=messages)
