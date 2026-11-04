#!/usr/bin/env python3
"""b84 APPROACH PICK: the end step's "polish before pick" for ONE other approach group, $0, accept-gated, under a hard time cap.

2026-10-30 (docs/b84_polish_before_pick.md section 3), adopted after the out-of-sample replay (section 1: the 3-group form
+0.011 a row on 64 samples, below the pre-registered bar; every win came from the best-stored other group g1) in its 1-extra-approach
variant with a time cap. harness/router.approach_step runs it inside the end step, once the end stage has settled the incumbent:

  groups    the row's candidates as the end stage reads them (endstage.collect over the row's steps and every pool.jsonl / bank.jsonl the
            router knows, entries with a stored score) grouped by APPROACH exactly as b80 step 0 / probe/b84/groups.py: each proof's lemma
            tokens (constructor names of the row's library dropped) plus its top-level splits; tokens at pool frequency 3%..97% form the
            key; groups = complete-link Jaccard >= 0.5 over the keys; groups ordered by their best stored score
  incumbent the group holding the incumbent's text, else the end stage's picked candidate, else the end step's input (the review output),
            else the group nearest by mean Jaccard of keys
  polish    the best-stored OTHER group (g1; --end-approach-groups N: g1..gN one after another) polished by the run's own $0 end stage
            (endstage.end_stage with router.end_stage_kwargs of --end-config, r10 in the final) on that group's lines alone, in a CHILD
            process (python3 harness/approach_pick.py --child JOB) whose whole process tree carries LRA_APPROACH_RUN=<tag>; the meter is the
            run's (its self-test record is handed over, so the child measures on the parent's path); every compile honours the run's
            compile slots (LRA_HBTOOL_SCRATCH / LRA_HBTOOL_SLOTS are inherited)
  cap       a HARD wall cap per row: min(--end-approach-seconds, what is left of the end stage's own clock for the row = the end config's
            sweep + tool phase seconds minus the time the end step already took). A child still running at the cap is killed (its process
            group, then every process tagged with its LRA_APPROACH_RUN, SIGTERM then SIGKILL) and its work abandoned
  gate      the polished proof replaces the incumbent only when: it is verified, Z 100 on every pin, passes final_writer.static_check
            (statement byte for byte, no forbidden construct), reads above the incumbent back to back on the run's end-stage meter (every
            pin, incumbent first) by scorer.accept.decide, passes the final writer's axiom audit (clean / skipped: no sorry, the sorry
            guard LRA_FORCE_WARN_SORRY=1 forced in the child), and the confirm read (router.end_guard: both back to back on the router's
            evaluator, every pin) is not lower and strictly above (delta > 0). Otherwise the incumbent stays byte-identical
  no harm   no model call; any error, timeout or refusal leaves the incumbent (the report says why); nothing is recorded or banked unless
            accepted

    python3 harness/approach_pick.py --child JOB.json      (the router starts it; writes JOB's "out" file)"""
from __future__ import annotations

import json, math, os, re, signal, subprocess, sys, time, uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TAG_ENV = "LRA_APPROACH_RUN"   # every process of one child polish (inherited through fork and exec: Lean compiles, the T5 workbench)
LO, HI, THR = 0.03, 0.97, 0.5  # b80 step 0 / probe/b84/groups.py: key-token pool frequency band, complete-link Jaccard
KILL_GRACE_S = 10.0
POLL_S = 0.5
MIN_SECONDS = 60.0             # less than this left of the row's end-stage clock: the pick is skipped ($0, nothing started)

# ----------------------------------------------------------------------------------------------------------------- approach signature
# probe/b84/s0_sig.py (= probe/b80/s0_sig.py, b80 step 0) verbatim: the grouping the out-of-sample replay measured.
TACTICS = set("""intro intros rintro obtain rcases cases induction fun_induction match with case case' next exact apply refine use exists
constructor assumption assumption' simp simp_all simp_rw simpa rw rwa grind omega decide aesop tauto trivial rfl apply_rfl ext funext congr
show have let calc by at only using generalizing all_goals any_goals first try repeat repeat' iterate rotate_left rotate_right swap pick_goal
on_goal focus unfold delta dsimp norm_num ring linarith nlinarith positivity field_simp push_cast exact_mod_cast norm_cast specialize
subst subst_vars injection injections contradiction exfalso by_contra by_cases split split_ifs left right existsi refine' fun from this
else then if do return sorry admit unhygienic with_reducible infer_instance inferInstance exacts symm trans change clear rename_i rename
set Exists And Or Iff Eq True False Not id fst snd mp mpr elim imp choose choose_spec intro_ irrefl absurd nomatch nofun termination_by
decreasing_by open in theorem lemma where at_least_one Type Prop Sort fun_prop gcongr bound filter_upwards conv lhs rhs arg enter
erw nth_rewrite nth_rw mono continuity measurability""".split())
AUTO = re.compile(r"^(a|h|x|y|z|ih|hx|hy|this|inst|motive|n|m|k|i|j|p|q|r|s|t|e|f|g|l|v|w|b|c|d)(_\d+|\d+|'+)?$|^[a-z]{1,3}\d*'*$|^[a-z]_\d+$")
IDENT = re.compile(r"(?<![\w.'])(\.?[A-Za-z_][\w'!?₀-₉]*(?:\.[A-Za-z_][\w'!?₀-₉]*)*)")
SPLIT = re.compile(r"^\s*(?:[·.]\s*)?(induction|cases|rcases|obtain|fun_induction|match|induction'|cases')\b([^\n]*)", re.M)
GENERIC = {"symm", "refl", "trans", "mp", "mpr", "imp", "elim", "intro", "choose_spec", "choose", "left", "right", "fst", "snd", "comp", "mk",
           "rec", "casesOn", "inl", "inr", "some", "none", "zip", "unzip", "head", "tail", "step", "store", "map", "eq", "ext"}
NOT_LEMMA = {"solve_by_elim", "apply_rules", "conv_lhs", "abstractProof", "simp_all!", "Exists.choose_spec", "choose_spec", "h_all", "this"}


def body(proof: str) -> str:
    i = proof.find(":= by")
    b = proof[i + 5:] if i >= 0 else proof
    return re.sub(r"\bunhygienic\b", "", b)


def lemma_tokens(proof: str) -> set[str]:
    out = set()
    b = re.sub(r"--[^\n]*", "", body(proof))
    for m in IDENT.finditer(b):
        t = m.group(1)
        if t.startswith("."):
            t = "." + t[1:].split(".")[-1]
            if t[1:] in TACTICS:
                continue
            out.add(t); continue
        parts = t.split(".")
        if len(parts) > 1 and parts[0][:1].islower() and not parts[0][:1] == "_":   # h.follow_fst: dot notation on a local
            if AUTO.match(parts[0]) or parts[0] not in TACTICS:
                f = parts[-1]
                if f not in TACTICS and len(f) > 2:
                    out.add("." + f)
                continue
        if t in TACTICS or AUTO.match(t):
            continue
        if len(parts) > 1 or "_" in t or re.search(r"[a-z][A-Z]", t) or t[:1].isupper():
            if t.strip("_") and not re.fullmatch(r"[a-z]+_\d+", t):
                out.add(t)
    return out


def splits(proof: str) -> tuple:
    sk = []
    for m in SPLIT.finditer(body(proof)):
        kw, rest = m.group(1), m.group(2)
        tgt = re.split(r"\b(with|generalizing|using)\b|:=|=>", rest)[0].strip()
        tgt = re.sub(r"[A-Za-z_][\w'₀-₉]*", lambda x: x.group(0) if (x.group(0)[:1].isupper() or "." in x.group(0)) else "_", tgt)
        sk.append(f"{kw} {tgt[:30]}".strip() if kw != "obtain" else "obtain")
    return tuple(sk)


def norm_lemma(t: str) -> str:
    parts = t.lstrip(".").split(".")
    last = parts[-1]
    return ".".join(parts[-2:]) if last in GENERIC and len(parts) > 1 else last


def lemma_set(proof: str, ctors) -> frozenset:
    out = set()
    for t in lemma_tokens(proof):
        n = norm_lemma(t)
        if n.split(".")[-1] in ctors or n in TACTICS or n in NOT_LEMMA:
            continue
        out.add(n)
    return frozenset(out)


def split_set(proof: str) -> frozenset:
    out = set()
    for s in splits(proof):
        kw = s.split()[0]
        tgt = s[len(kw):].strip()
        if kw in ("induction", "fun_induction", "induction'"):
            out.add("induction")
        elif kw in ("cases", "rcases") and re.match(r"[A-Z][\w'.]*", tgt):
            out.add(f"cases {tgt.split()[0]}")
    return frozenset(out)


_CTORS: dict = {}
_INDUCTIVE = re.compile(r"^(?:[\w@\[\] ]*\s)?inductive\s[^\n]*\n((?:[ \t]*(?:\||--)[^\n]*\n|[ \t]+[^\n|][^\n]*\n)*)", re.M)
_CTOR = re.compile(r"^\s*\|\s*([A-Za-z_][\w'₀-₉]*)", re.M)


def library_dir(row: dict) -> Path | None:
    """The row's library sources on its newest pin: envs/<library>-<pin>/<the top directory of the row's file_path> (b84 used the same
    newest pins: cslib v4.33.0-rc2, strata v4.29.1, physlib v4.32.0, arklib v4.31.0). None for a row without one (PutnamBench)."""
    try:
        from scorer import compile as C
        from probe.verify_candidates import newest_first
        top = str(row.get("file_path") or "").split("/")[0]
        if not top or row.get("source") not in C.PROJECT_DIRS:
            return None
        d = C.project_env_dir(row["source"], newest_first(row["version_info"])[0]) / top
        return d if d.is_dir() else None
    except Exception:  # noqa: BLE001
        return None


def ctor_names(row: dict) -> frozenset:
    """Constructor names of the row's library (a text scan of `inductive` blocks, as b80 step 0): a lemma token whose last component is one
    is the statement's vocabulary, not an approach. Empty when the sources are not there (the grouping then keeps those tokens)."""
    d = library_dir(row)
    if d is None:
        return frozenset()
    k = str(d)
    if k in _CTORS:
        return _CTORS[k]
    out = set()
    for f in sorted(d.rglob("*.lean")):
        try:
            txt = f.read_text(errors="ignore")
        except OSError:
            continue
        for m in _INDUCTIVE.finditer(txt):
            for c in _CTOR.finditer(m.group(1)):
                out.add(c.group(1))
    _CTORS[k] = frozenset(out)
    return _CTORS[k]


# ------------------------------------------------------------------------------------------------------------------------- grouping
def _finite(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def jac(a, b) -> float:
    return 1.0 if not (a or b) else len(a & b) / len(a | b)


def proof_key(proof: str, ctors) -> frozenset:
    return lemma_set(proof, ctors) | split_set(proof)


def cluster(entries: list[dict], ctors) -> tuple[list[list[dict]], dict, frozenset]:
    """probe/b84/groups.cluster on `entries` ({sha, proof, score, ...}, a stored score each): (groups, sha -> key, key tokens). Each group
    is ordered by stored score (best first), the groups by their best stored score."""
    toks = {x["sha"]: proof_key(x["proof"], ctors) for x in entries}
    c = Counter()
    for v in toks.values():
        c.update(v)
    n = len(entries)
    key = frozenset(k for k, v in c.items() if LO * n <= v <= HI * n)
    ks = {s: frozenset(v & key) for s, v in toks.items()}
    uniq = defaultdict(list)
    for x in entries:
        uniq[ks[x["sha"]]].append(x)
    C = [[k] for k in sorted(uniq, key=lambda k: sorted(k))]
    while True:
        best = None
        for i in range(len(C)):
            for j in range(i + 1, len(C)):
                s = min(jac(a, b) for a in C[i] for b in C[j])
                if s >= THR and (best is None or s > best[0]):
                    best = (s, i, j)
        if not best:
            break
        _, i, j = best
        C[i] = C[i] + C[j]
        del C[j]
    groups = [sorted([x for k in cl for x in uniq[k]], key=lambda x: -x["score"]) for cl in C]
    return sorted(groups, key=lambda g: -g[0]["score"]), ks, key


def scored(cands: list[dict]) -> list[dict]:
    """The end stage's candidates (endstage.collect entries) that carry a stored score, as the grouping reads them."""
    out, seen = [], set()
    for c in cands:
        p = (c.get("proof") or "").strip()
        if not p or not _finite(c.get("score")) or c.get("sha") in seen:
            continue
        seen.add(c.get("sha"))
        out.append({"sha": c["sha"], "proof": p, "score": float(c["score"]), "tokens": c.get("tokens"), "heartbeats": c.get("heartbeats"),
                    "origins": list(c.get("origins") or [])})
    return out


def picked_sha(res: dict) -> str | None:
    """The sha of the candidate the end stage picked (its banked pick decision), when it says."""
    for d in (res or {}).get("decisions") or []:
        if isinstance(d, dict) and d.get("op") == "pick" and d.get("banked") and d.get("sha"):
            return d["sha"]
    return None


def incumbent_group(groups: list[list[dict]], ks: dict, key: frozenset, ctors, shas: list[tuple[str, str | None]], inc_proof: str):
    """(index of the incumbent's group, how): the first of `shas` [(label, sha)] held by a group, else the group nearest the incumbent's
    key by mean Jaccard (probe/b84/groups.py's order: the final's sha, the replay's input, nearest key)."""
    for label, s in shas:
        if not s:
            continue
        for i, g in enumerate(groups):
            if any(x["sha"] == s for x in g):
                return i, label
    fk = frozenset(proof_key(inc_proof, ctors) & key)
    return max(range(len(groups)), key=lambda i: sum(jac(fk, ks[x["sha"]]) for x in groups[i]) / len(groups[i])), "nearest key"


def plan(cands: list[dict], row: dict, inc_proof: str, shas: list[tuple[str, str | None]], n_other: int = 1) -> dict:
    """The groups and the other groups to polish. {"groups": [{n, best, sha}], "incumbent": i, "how", "jobs": [{gid, lines}], "status"}."""
    from harness import endstage as E
    ents = scored(cands)
    out = {"candidates": len(ents), "groups": [], "incumbent": None, "how": None, "jobs": []}
    if len(ents) < 2:
        return dict(out, status="fewer than two scored candidates: one approach")
    ct = ctor_names(row)
    G, ks, key = cluster(ents, ct)
    out["groups"] = [{"n": len(g), "best": round(g[0]["score"], 4), "sha": g[0]["sha"]} for g in G]
    out["key_tokens"] = len(key)
    if len(G) < 2:
        return dict(out, status="one approach group")
    inc_sha = E.sha(inc_proof) if inc_proof else None
    gi, how = incumbent_group(G, ks, key, ct, [("incumbent", inc_sha)] + list(shas), inc_proof or "")
    others = [i for i in range(len(G)) if i != gi]
    out.update(incumbent=gi, how=how)
    for k, i in enumerate(others[:max(0, int(n_other))]):
        out["jobs"].append({"gid": f"g{k + 1}", "group": i, "n": len(G[i]), "best": G[i][0]["score"],
                            "lines": [{"proof": x["proof"], "score_exact": x["score"], "tokens": x["tokens"], "heartbeats": x["heartbeats"],
                                       "run_id": (x["origins"] or ["?"])[0]} for x in G[i]]})
    return dict(out, status="planned")


# --------------------------------------------------------------------------------------------------------------------------- child
def child_main(job_path: str) -> int:
    """Polish one group's lines with the run's end stage (probe/b84/polish.py's call): endstage.collect over the lines alone (seed included)
    -> endstage.end_stage(..., checkpoint_bests={}, **router.end_stage_kwargs(--end-config)) on a Meter built like router._end_meter whose
    run-start self-test record is the parent's. Writes job["out"] atomically."""
    job = json.loads(Path(job_path).read_text())
    out = Path(job["out"])
    t0 = time.time()
    logf = open(job["log"], "a") if job.get("log") else None

    def log(m):
        if logf is not None:
            logf.write(f"[{time.strftime('%H:%M:%S')}] {m}\n"); logf.flush()

    def write(rec):
        tmp = out.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, default=str))
        tmp.replace(out)
    try:
        os.environ["LRA_FORCE_WARN_SORRY"] = "1"   # the sorry guard (b71 R1) on every compile of the polish
        import argparse
        from harness import endstage as E
        from harness import router as RT
        row, hbs, seed = job["row"], dict(job["heartbeats"]), job["seed"]
        with E._LOCK:
            E._RUN["tests"].update(job.get("meter_tests") or {})
            if job.get("meter_fallback") and not E._RUN["fallback"]:
                E._RUN["fallback"] = job["meter_fallback"]
        meter = E.Meter(row, hbs, log=log)
        meter.self_test(seed)   # cached from the parent's record (0 compiles) unless a pin is missing there
        A = argparse.Namespace(end_config=job["end_config"], end_config_sha256=job.get("end_config_sha256"),
                               end_k=int(job.get("end_k") or 6), end_max_compiles=int(job.get("end_max_compiles") or 60))
        kw = RT.end_stage_kwargs(A, E)
        cands = E.collect(row["name"], steps={}, pool_lines=job["lines"], seed=seed)
        res = dict(E.end_stage(row, seed, cands, meter, checkpoint_bests={}, log=log, **kw) or {})
        M = res.get("metrics") if isinstance(res.get("metrics"), dict) else {}
        verified = (bool(res["verified"]) if "verified" in res else res.get("stage") not in (None, "unmeasured")) \
            and isinstance(res.get("proof"), str) and bool(res["proof"].strip())
        write({"ok": True, "verified": verified, "proof": res.get("proof"), "stage": res.get("stage"),
               "metrics": {k: M.get(k) for k in ("score", "score_exact", "tokens", "heartbeats", "L", "H", "Z", "compat", "meter")},
               "compiles": res.get("compiles"), "candidates": len(cands), "meter": meter.path, "self_test_cached": bool((meter.test or {}).get("cached")),
               "seconds": round(time.time() - t0, 1)})
        log(f"approach child: {res.get('stage')} -> {M.get('score_exact')} ({res.get('compiles')} compiles, {time.time() - t0:.0f} s)")
        return 0
    except Exception as e:  # noqa: BLE001
        try:
            write({"ok": False, "error": f"{type(e).__name__}: {str(e)[:300]}", "seconds": round(time.time() - t0, 1)})
        except Exception:  # noqa: BLE001
            pass
        log(f"approach child raised {type(e).__name__}: {str(e)[:300]}")
        return 1
    finally:
        if logf is not None:
            logf.close()


# -------------------------------------------------------------------------------------------------------------------------- parent
def tagged_pids(tag: str, proc_root: Path = Path("/proc")) -> list[int]:
    needle, me, out = f"{TAG_ENV}={tag}".encode(), os.getpid(), []
    try:
        entries = [d for d in proc_root.iterdir() if d.name.isdigit() and int(d.name) != me]
    except OSError:
        return out
    for d in entries:
        try:
            if needle in (d / "environ").read_bytes().split(b"\0"):
                out.append(int(d.name))
        except (OSError, ValueError):
            continue
    return out


def _signal(pids, sig) -> int:
    n = 0
    for p in pids:
        try:
            os.kill(p, sig); n += 1
        except OSError:
            pass
    return n


def kill_tree(proc: subprocess.Popen, tag: str, grace: float = KILL_GRACE_S) -> dict:
    """SIGTERM the child's process group and every process tagged with its TAG_ENV (Lean compiles run in their own sessions), wait up to
    `grace`, then SIGKILL what is left. Never raises."""
    rec = {"term": 0, "killed": 0}
    try:
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            pass
        rec["term"] = _signal(tagged_pids(tag), signal.SIGTERM)
        t_end = time.monotonic() + max(0.0, grace)
        while time.monotonic() < t_end and (proc.poll() is None or tagged_pids(tag)):
            time.sleep(0.25)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        rec["killed"] = _signal(tagged_pids(tag), signal.SIGKILL)
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            pass
    except Exception as e:  # noqa: BLE001
        rec["error"] = f"{type(e).__name__}: {str(e)[:120]}"
    return rec


def run_child(job: dict, cap_s: float, workdir: Path, stop=None, python: str | None = None, argv: list | None = None) -> dict:
    """Run one group's polish in a child under a hard wall cap. Returns {"status": done | cap | error | stopped, "seconds", "result"?,
    "kill"?}. `stop` (a threading.Event): the router is terminating: the child is killed at once. `argv` (tests): the child command, the
    job file appended. Never raises."""
    t0 = time.monotonic()
    tag = uuid.uuid4().hex
    proc = None
    try:
        workdir.mkdir(parents=True, exist_ok=True)
        jp = workdir / f"{job['gid']}.job.json"
        job = dict(job, out=str(workdir / f"{job['gid']}.result.json"), log=str(workdir / f"{job['gid']}.log"))
        Path(job["out"]).unlink(missing_ok=True)
        jp.write_text(json.dumps(job, ensure_ascii=False, default=str))
        env = dict(os.environ, **{TAG_ENV: tag, "LRA_FORCE_WARN_SORRY": "1", "PYTHONUNBUFFERED": "1"})
        with open(workdir / f"{job['gid']}.stdout", "ab") as so:
            cmd = [*argv, str(jp)] if argv else [python or sys.executable, "-u", str(Path(__file__).resolve()), "--child", str(jp)]
            proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env,
                                    stdin=subprocess.DEVNULL, stdout=so, stderr=subprocess.STDOUT, start_new_session=True)
        status = None
        while proc.poll() is None:
            if stop is not None and stop.is_set():
                status = "stopped"; break
            if time.monotonic() - t0 >= cap_s:
                status = "cap"; break
            time.sleep(POLL_S)
        if status is not None:
            k = kill_tree(proc, tag)
            return {"status": status, "seconds": round(time.monotonic() - t0, 1), "kill": k}
        left = tagged_pids(tag)   # a compile the child left behind (it should not): ended here
        if left:
            _signal(left, signal.SIGKILL)
        try:
            res = json.loads(Path(job["out"]).read_text())
        except (OSError, ValueError) as e:
            return {"status": "error", "error": f"no result ({type(e).__name__}; child exit {proc.returncode})",
                    "seconds": round(time.monotonic() - t0, 1)}
        if not res.get("ok"):
            return {"status": "error", "error": res.get("error") or f"child exit {proc.returncode}", "seconds": round(time.monotonic() - t0, 1)}
        return {"status": "done", "seconds": round(time.monotonic() - t0, 1), "result": res}
    except Exception as e:  # noqa: BLE001
        k = kill_tree(proc, tag) if proc is not None and proc.poll() is None else None
        return {"status": "error", "error": f"{type(e).__name__}: {str(e)[:200]}", "seconds": round(time.monotonic() - t0, 1),
                **({"kill": k} if k else {})}


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) == 2 and argv[0] == "--child":
        return child_main(argv[1])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
