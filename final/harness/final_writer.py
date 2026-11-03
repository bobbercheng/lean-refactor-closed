"""b65-final (audit C1 + C2, docs/b65_failure_audit.md; 2026-10-27 no-harm rule: a stopped, failed or over-cap LLM request must not harm
the run or its results): the router's submission writer. Before it, nothing turned finals.json into the upload file,
and finals.json itself was written once, at the very end: a crash, a kill, a short stop or a fatal pin left no output at all.

  <run dir>/submission.jsonl        {"name", "proof"} per row, in the problem file's order (the Arena upload format; a missing row scores 0)
  <run dir>/submission_check.json   per row: the candidate written, its verdict, every candidate tried (labels, sha, verdicts; no proof text),
                                    and the compile verdict cache (row|sha -> ok / bad)

When it is written (harness/router.py):
  start        seed-only (the benchmark's original proof, `src`, for every row) before any paid step; a resume keeps the rows an earlier
               invocation wrote and fills only the missing ones
  checkpoint   each row's checkpoint cleanup output, statically checked (verified by the cleanup that produced it; no extra compile)
  row done     each row's final as post_row returns it, compile-checked (below)
  exit         from main's finally: on every exit path (normal end, a short stop or a confirmed pin, an exception, SIGTERM): every row again,
               compile-checked except on SIGTERM (static checks and cached verdicts only: the stop timeout is short)
Every write is the whole file, by temp file + os.replace under a lock, so a reader (or a SIGKILL) never sees a torn file.

The pick per row: the first candidate (the router's final first, then the row's other verified items by score, at most MAX_CHECKED compile
checks) that is non-empty, starts with the identical statement (scorer.tokenize.split_declaration), has no forbidden construct
(scorer.forbidden) and compiles on every listed pin; else the seed. A compile that times out or whose memgate gave up (both read as
timed_out), or an environment error (a missing toolchain or env: infrastructure, not the proof), or (review 2026-10-27) a Lean process
killed by a signal (scorer.compile: "lean exit -9": the runaway guard's pressure kill or the OOM killer, both armed on the VM, most likely on
the exit path's burst of checks) is UNKNOWN: retried once, and if it stays unknown the candidate is kept (every candidate was verified by
the stage that produced it): never a demotion to the seed (a BAD verdict is cached in submission_check.json for the rest of the run).
No heavy imports at module level (scorer only inside the checks).

b71 R1 (2026-10-28, R1 of docs/tail_signal_study.md; docs/b71_final.md): the FINAL AXIOM AUDIT. A candidate whose compile
verdict is ok is audited before it is written (audit_fn; the router's: router_audit_fn = scorer.compile.audit_axioms on EVERY pin of the
row, the declaration compiled unmeasured with warn.sorry forced on + `#print axioms`): it is flagged ("sorry") when Lean's sorry message
appears on its lines or it names a way to hide that message, or when sorryAx is among its axioms on a pin where the row's own seed does
not depend on sorryAx (an axiom inherited from the project, which the seed shares, is not the candidate's). A flagged candidate is BAD
(cached), so the pick falls back to the row's next verified candidate that passes (its best banked proof), else the seed. An audit that
cannot decide (an exception, a timeout, an unresolved name, errors the compile verdict did not see) is "unknown": the candidate is kept
(the old behaviour) and the reason logged; never a demotion. Each audit is bounded (AUDIT_TIMEOUT per pin, no retry); the SIGTERM path
(compile_ok False) audits nothing new (cached verdicts still apply). submission_check.json carries per row "audit" (clean / unknown /
skipped / none) and "audit_fallback" (a flagged candidate was passed over), the audit cache ("audits", name|sha -> status) and the counts
("audit_counts")."""
from __future__ import annotations

import hashlib, json, os, re, threading, time
from pathlib import Path

SUBMISSION = "submission.jsonl"
CHECKS = "submission_check.json"
MAX_CHECKED = 4          # compile-checked candidates per row before the seed (bounded wall time on the exit path)
AUDIT_TIMEOUT = 600      # b71 R1: seconds per pin of one axiom-audit compile (unmeasured; the audit is one compile per pin)
CLEAN, SORRY = "clean", "sorry"   # b71 R1 audit statuses (with UNKNOWN and "skipped": a module file, sorry message check only)
OK, BAD, UNKNOWN = "ok", "bad", "unknown"
KILLED = re.compile(r"lean exit -\d+")   # scorer.compile._parse: a Lean process that a signal ended, with no error message of its own


def sha12(text) -> str | None:
    return hashlib.sha256(text.encode()).hexdigest()[:12] if isinstance(text, str) else None


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def read_submission(path: Path) -> dict:
    """name -> proof of a submission file ({} when missing or unreadable; a line that is not {"name", "proof"} with a non-empty proof is
    skipped)."""
    out = {}
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return {}
    for l in lines:
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if isinstance(d, dict) and isinstance(d.get("name"), str) and isinstance(d.get("proof"), str) and d["proof"].strip():
            out[d["name"]] = d["proof"]
    return out


def static_check(proof, statement: str | None) -> str | None:
    """None when the proof is non-empty, starts with the identical statement and has no forbidden construct; else why not."""
    if not isinstance(proof, str) or not proof.strip():
        return "empty"
    if statement is None:
        return None
    from scorer.tokenize import split_declaration
    from scorer.forbidden import check_forbidden
    body = split_declaration(proof.rstrip(), statement)
    if body is None:
        return "statement differs"
    bad = check_forbidden(body)
    return f"forbidden: {bad}" if bad else None


def _infra(err: str) -> bool:
    """An error that says nothing about the proof: a missing toolchain / env, the compile budget, a Lean killed by a signal (review)."""
    return err.startswith("environment:") or "compile budget exhausted" in err or bool(KILLED.search(err))


def audit_verdict(audit_pin, versions: list, proof: str, seed_has_sorry=None) -> tuple[str, str, dict]:
    """b71 R1: (clean | sorry | skipped | unknown, why, {pin: what}) of one candidate from audit_pin(version, proof) ->
    scorer.compile.AxiomAudit-like (sorry_warning, switch, axioms, decl_errors, skipped, compile.timed_out) on every pin.
    seed_has_sorry(version) -> True / False / None (unknown): whether the row's own seed depends on sorryAx there (module docstring)."""
    per, unknown, skipped = {}, [], []
    for v in versions:
        try:
            a = audit_pin(v, proof)
        except Exception as e:  # noqa: BLE001  (the audit itself broke: unknown, never a demotion)
            per[v] = "error"; unknown.append(f"{v}: {type(e).__name__}: {str(e)[:80]}"); continue
        c = getattr(a, "compile", None)
        if getattr(a, "switch", False) or getattr(a, "sorry_warning", False):
            per[v] = SORRY
            return SORRY, f"axiom audit on {v}: the declaration uses sorry (Lean's sorry message, warn.sorry on)", per
        if c is not None and getattr(c, "timed_out", False):
            per[v] = "timeout"; unknown.append(f"{v}: the audit compile timed out"); continue
        axs = getattr(a, "axioms", None)
        if axs is not None and "sorryAx" in axs:
            inherited = None
            if seed_has_sorry is not None:
                try:
                    inherited = seed_has_sorry(v)
                except Exception:  # noqa: BLE001
                    inherited = None
            if inherited is False:
                per[v] = SORRY
                return SORRY, f"axiom audit on {v}: depends on sorryAx (the row's seed does not)", per
            per[v] = "inherited" if inherited else "sorryAx?"
            if not inherited:
                unknown.append(f"{v}: sorryAx without a sorry message and no seed to compare")
            continue
        if getattr(a, "decl_errors", None):
            per[v] = "errors"; unknown.append(f"{v}: the audit compile reports errors ({str(a.decl_errors[0])[:80]})"); continue
        if getattr(a, "skipped", None):
            per[v] = f"skipped:{a.skipped}"; skipped.append(v); continue
        if axs is None:
            per[v] = "no axioms"; unknown.append(f"{v}: no #print axioms output"); continue
        per[v] = CLEAN
    if unknown:
        return UNKNOWN, "; ".join(unknown)[:200], per
    if skipped:
        return "skipped", f"sorry message check only on {', '.join(skipped)} (module file or no name); no sorry", per
    return CLEAN, f"no sorry on {len(versions)} pin(s)", per


def compile_verdict(ev_full, ev_pin, versions: list, proof: str) -> tuple[str, str]:
    """One compile check: ev_full(proof) reads every pin (an evaluator's full reading: ok, compat, timed_out, error); ev_pin(version, proof)
    reads one pin (a non-primary pin that failed is re-read alone, so a timeout there is told from an error). (ok | bad | unknown, why)."""
    r = ev_full(proof) or {}
    err = str(r.get("error") or "")
    if r.get("timed_out"):
        return UNKNOWN, "the compile timed out (or memgate gave up)"
    if not r.get("ok"):
        if _infra(err):
            return UNKNOWN, err[:160]
        return BAD, (err or "does not compile")[:160]
    compat = r.get("compat") or {}
    unknown = []
    for v in versions:
        if compat.get(v) is True:
            continue
        rv = ev_pin(v, proof) or {}
        if rv.get("ok"):
            continue
        e = str(rv.get("error") or "")
        if rv.get("timed_out") or _infra(e) or v not in compat:
            unknown.append(v); continue
        return BAD, f"fails on {v}: {(e or 'does not compile')[:120]}"
    if unknown:
        return UNKNOWN, f"no reading on {', '.join(unknown)} (timed out, memgate or environment)"
    return OK, f"compiles on {len(versions)} pin(s)"


class Writer:
    """One router run's submission file. seeds: name -> the benchmark's proof; statements: name -> statement; compile_fn(name, proof) ->
    (verdict, why) or None (no compile check: static only). Thread-safe (rows finish in parallel)."""

    def __init__(self, run_dir: Path, names: list, seeds: dict, statements: dict, compile_fn=None, log=print, audit_fn=None):
        self.dir, self.names, self.seeds, self.statements = Path(run_dir), list(names), dict(seeds), dict(statements)
        self.path, self.check_path = self.dir / SUBMISSION, self.dir / CHECKS
        self.compile_fn, self.log = compile_fn, log
        self.audit_fn = audit_fn   # b71 R1: (name, proof) -> (clean | sorry | skipped | unknown, why); None: no audit (as before)
        self.lock = threading.Lock()
        try:
            ck = json.loads(self.check_path.read_text())
        except (OSError, ValueError):
            ck = {}
        self.verdicts: dict = dict(ck.get("verdicts") or {})   # "name|sha" -> {"v", "why", "at"} (ok / bad only: unknown is retried)
        self.rows: dict = dict(ck.get("rows") or {})           # name -> the pick's record
        self.audits: dict = dict(ck.get("audits") or {})       # b71: "name|sha" -> {"a": status, "why", "at"} (decided statuses only)
        self.audit_unknown: dict = {}   # b71 review: "name|sha" -> the undecided audit of this process (in memory: no retry in this run,
        #                                 a resumed writer audits it once more; an undecided audit keeps the candidate either way)
        self.lines: dict = {}                                  # name -> the proof written

    # ---------------------------------------------------------------------------------------------------------------- the file
    def start(self) -> dict:
        """At router start: a valid earlier file's rows stay (a resume), every other row gets its seed. Returns the counts."""
        old = read_submission(self.path)
        with self.lock:
            kept = 0
            for n in self.names:
                p = old.get(n)
                if p is not None and static_check(p, self.statements.get(n)) is None:
                    self.lines[n] = p; kept += 1
                else:
                    self.lines[n] = self.seeds.get(n) or p or ""
                    self.rows.setdefault(n, {"pick": "seed", "verdict": "seed", "at": _now()})
            self._write()
        return {"rows": len(self.names), "kept": kept, "seeded": len(self.names) - kept}

    def _write(self) -> None:   # under self.lock
        lines = [json.dumps({"name": n, "proof": self.lines.get(n) or self.seeds.get(n) or ""}, ensure_ascii=False) for n in self.names]
        _atomic(self.path, "".join(l + "\n" for l in lines))
        rows = {n: self.rows.get(n) for n in self.names}
        ac: dict = {}
        for r in rows.values():   # b71 R1: the audit status of each row's written line (counts only)
            k = (r or {}).get("audit") or ("seed" if (r or {}).get("pick") == "seed" else "not audited")
            ac[k] = ac.get(k, 0) + 1
        ac["fallback"] = sum(1 for r in rows.values() if (r or {}).get("audit_fallback"))
        _atomic(self.check_path, json.dumps({"at": _now(), "rows": rows, "verdicts": self.verdicts, "audits": self.audits,
                                             "audit_counts": ac if self.audit_fn is not None else None},
                                            ensure_ascii=False, indent=1) + "\n")

    # ---------------------------------------------------------------------------------------------------------------- the pick
    def verdict(self, name: str, proof: str, compile_ok: bool = True) -> tuple[str, str]:
        """ok / bad / unknown for one candidate: the cache, else (compile_ok) a compile check retried once when unknown; without a compile
        (compile_ok False or no compile_fn) a candidate the cache does not know is `unchecked` (kept: verified upstream)."""
        key = f"{name}|{sha12(proof)}"
        c = self.verdicts.get(key)
        if c:
            v, why = c["v"], c.get("why") or "cached"
            if v == OK and compile_ok:
                return self._audited(name, proof, key, v, why)
            return v, why
        if not compile_ok or self.compile_fn is None:
            return "unchecked", "no compile on this path (verified by the stage that produced it)"
        v, why = UNKNOWN, ""
        for k in range(2):   # an unknown reading (timeout, memgate give-up, environment) is retried once
            try:
                v, why = self.compile_fn(name, proof)
            except Exception as e:  # noqa: BLE001  (the check itself broke: unknown, never a demotion)
                v, why = UNKNOWN, f"check failed: {type(e).__name__}: {str(e)[:120]}"
            if v != UNKNOWN:
                break
            if k == 0:
                self.log(f"{name[:40]}: submission check unknown ({why}); retrying once")
        if v in (OK, BAD):
            with self.lock:
                self.verdicts[key] = {"v": v, "why": why, "at": _now()}
        if v == OK:
            return self._audited(name, proof, key, v, why)
        return v, why

    def _audited(self, name: str, proof: str, key: str, v: str, why: str) -> tuple[str, str]:
        """b71 R1: an ok candidate through the axiom audit (module docstring): flagged -> BAD (cached), else (v, why) unchanged."""
        if self.audit_fn is None:
            return v, why
        a = self.audits.get(key) or self.audit_unknown.get(key)
        if a is None:
            try:
                st, aw = self.audit_fn(name, proof)
            except Exception as e:  # noqa: BLE001  (the audit itself broke: unknown, the candidate is kept)
                st, aw = UNKNOWN, f"audit failed: {type(e).__name__}: {str(e)[:120]}"
            a = {"a": st, "why": str(aw)[:200], "at": _now()}
            if st in (CLEAN, SORRY, "skipped"):
                with self.lock:
                    self.audits[key] = a
            else:   # b71 review: not audited again in this process (the docstring's "no retry": a timed-out audit cost up to
                #     AUDIT_TIMEOUT per pin at the row's end and again on the exit path's all_rows)
                with self.lock:
                    self.audit_unknown[key] = a
                self.log(f"{name[:40]}: axiom audit unknown ({str(aw)[:160]}); the candidate is kept (no harm)")
        if a["a"] == SORRY:
            why = f"axiom audit: {a['why']}"[:200]
            with self.lock:
                self.verdicts[key] = {"v": BAD, "why": why, "at": _now(), "audit": SORRY}
            self.log(f"{name[:40]}: axiom audit flagged a candidate ({a['why'][:120]}); the next verified candidate is tried")
            return BAD, why
        return v, why

    def pick(self, name: str, cands: list, compile_ok: bool = True) -> tuple[str, dict]:
        """cands: [(label, item)] in preference order (the router's final first). Returns (proof, record)."""
        st, seed = self.statements.get(name), self.seeds.get(name)
        tried, seen, checked = [], set(), 0
        for label, it in cands:
            proof = (it or {}).get("proof")
            h = sha12(proof)
            if h is None or h in seen:
                continue
            seen.add(h)
            why = static_check(proof, st)
            if why:
                tried.append({"label": label, "sha": h, "verdict": "static", "why": why}); continue
            if seed is not None and proof.strip() == seed.strip():
                break   # the seed itself: written below, no check needed
            if checked >= MAX_CHECKED and f"{name}|{h}" not in self.verdicts:
                tried.append({"label": label, "sha": h, "verdict": "skipped", "why": f"{MAX_CHECKED} candidates checked"}); continue
            v, why = self.verdict(name, proof, compile_ok)
            checked += 1
            au = (self.audits.get(f"{name}|{h}") or {}).get("a")
            tried.append({"label": label, "sha": h, "verdict": v, "why": why[:160], **({"audit": au} if au else {})})
            if v == BAD:
                continue
            rec = {"pick": label, "verdict": v, "sha": h, "score": (it or {}).get("score"), "tried": tried, "at": _now()}
            if self.audit_fn is not None and v == OK:   # b71 R1: the written line's audit (unknown: kept, the old behaviour)
                rec["audit"] = au or UNKNOWN
            if any(t.get("audit") == SORRY for t in tried):
                rec["audit_fallback"] = True
            return proof, rec
        if seed:
            rec = {"pick": "seed", "verdict": "seed", "sha": sha12(seed), "tried": tried, "at": _now()}
            if any(t.get("audit") == SORRY for t in tried):
                rec["audit_fallback"] = True
            return seed, rec
        # no seed known (a generic --input run without `src`): the first statically valid candidate, else the old line
        for label, it in cands:
            p = (it or {}).get("proof")
            if static_check(p, st) is None:
                return p, {"pick": label, "verdict": "no seed", "sha": sha12(p), "tried": tried, "at": _now()}
        return self.lines.get(name) or "", {"pick": "previous", "verdict": "no seed", "tried": tried, "at": _now()}

    def row(self, name: str, cands: list, compile_ok: bool = True) -> dict:
        """One row's pick into the file (rewritten whole, atomically). Never raises: a failure keeps the row's previous line."""
        try:
            proof, rec = self.pick(name, cands, compile_ok)
        except Exception as e:  # noqa: BLE001
            self.log(f"{name[:40]}: submission line kept ({type(e).__name__}: {str(e)[:120]})")
            return {}
        with self.lock:
            if proof:
                self.lines[name] = proof
            self.rows[name] = rec
            try:
                self._write()
            except OSError as e:
                self.log(f"{name[:40]}: submission file not written ({type(e).__name__}: {e})")
        return rec

    def all_rows(self, cands_of, compile_ok: bool = True, jobs: int = 1) -> dict:
        """Every row (cands_of(name) -> its candidates; a row whose candidates cannot be read keeps its line). Returns the counts."""
        def one(n):
            try:
                c = cands_of(n)
            except Exception as e:  # noqa: BLE001
                self.log(f"{n[:40]}: submission candidates not read ({type(e).__name__}: {str(e)[:120]}); line kept")
                return {}
            return self.row(n, c, compile_ok)
        if jobs > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(jobs) as ex:
                recs = list(ex.map(one, self.names))
        else:
            recs = [one(n) for n in self.names]
        with self.lock:
            self._write()
        cnt: dict = {}
        for r in recs:
            cnt[(r or {}).get("verdict") or "kept"] = cnt.get((r or {}).get("verdict") or "kept", 0) + 1
        return cnt


def router_audit_fn(rows: dict, timeout: int = AUDIT_TIMEOUT, audit=None):
    """b71 R1: audit_fn for Writer: scorer.compile.audit_axioms on every pin of the row (newest first), the row's seed audited on a pin only
    when a candidate shows sorryAx there without a sorry message (memoised per row and pin). `audit` (tests): replaces audit_axioms."""
    from probe.verify_candidates import newest_first
    memo: dict = {}
    lock = threading.Lock()

    def aud(row, proof, v):
        if audit is not None:
            return audit(row, proof, v)
        from scorer.compile import audit_axioms
        return audit_axioms(row, proof, v, timeout=int(timeout))

    def fn(name, proof):
        row = rows[name]
        versions = newest_first(row["version_info"])
        seed = row.get("src")

        def seed_has_sorry(v):
            k = (name, v)
            with lock:
                if k in memo:
                    return memo[k]
            try:
                a = aud(row, seed, v)
                r = None if getattr(a, "axioms", None) is None else ("sorryAx" in a.axioms or bool(getattr(a, "sorry_warning", False)))
            except Exception:  # noqa: BLE001
                r = None
            with lock:
                memo[k] = r
            return r
        st, why, _per = audit_verdict(lambda v, p: aud(row, p, v), versions, proof, seed_has_sorry if seed else None)
        return st, why
    return fn


def router_compile_fn(evaluator, rows: dict):
    """compile_fn for Writer over the router's evaluator (a factory, or an object with .bound): every pin of the row (newest first)."""
    from probe.verify_candidates import newest_first

    def ev_of(name, versions):
        e = evaluator() if callable(evaluator) and not hasattr(evaluator, "bound") else evaluator
        return e.bound(name, versions)

    def fn(name, proof):
        versions = newest_first(rows[name]["version_info"])
        full = ev_of(name, versions)
        return compile_verdict(lambda p: full(p, True), lambda v, p: ev_of(name, [v])(p, False), versions, proof)
    return fn
