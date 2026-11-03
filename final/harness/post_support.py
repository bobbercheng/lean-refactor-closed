#!/usr/bin/env python3
"""Support pieces of the post-step (infra/closed_package/post_step.py) that harness/open_post.py takes from the open package's module
harness/open_package.py, which this closed package does not have. Copied verbatim from our development repository, commit
5cb18d3bb80fc3ede09527eb36adf0ecf7759146 (branch open-post, the commit the post-step's own files come from), harness/open_package.py:
  SORRY_GUARD_ENV   line 153    the sorry guard's environment (the same variable as run_final.SORRY_GUARD_ENV of this package)
  git_trust         lines 156-164
  AUDIT_TIMEOUT_S   line 165
  AUDIT_MIN_PIN_S   line 168
  audit_proof       lines 2513-2562   (the `#print axioms` sorry audit of one proof on every pin; scorer.compile.audit_axioms, unchanged)
Nothing else of that module is used or copied. The toolchain order (newest_first) is this package's own probe/verify_candidates.py, the
same file as in that commit."""
from __future__ import annotations

import time

SORRY_GUARD_ENV = {"LRA_FORCE_WARN_SORRY": "1"}


def git_trust(env) -> None:
    """rc3 (2026-11-01, rc2's box smoke): Lake runs git inside the env checkouts (.lake/packages/*), and git refuses a repository owned by
    another user ("detected dubious ownership"), so every lake compile failed (lean exit 1) when the process user differed from the files'
    owner (root vs ubuntu on a vast box; uid-mapped Shifter / podman-hpc on shared storage would do the same). safe.directory=* for this
    process tree through git's GIT_CONFIG_COUNT variables (git >= 2.31), appended after any pairs already set; no config file is written."""
    n = int(env.get("GIT_CONFIG_COUNT") or 0)
    if any(env.get(f"GIT_CONFIG_KEY_{i}") == "safe.directory" and env.get(f"GIT_CONFIG_VALUE_{i}") == "*" for i in range(n)):
        return
    env[f"GIT_CONFIG_KEY_{n}"] = "safe.directory"; env[f"GIT_CONFIG_VALUE_{n}"] = "*"; env["GIT_CONFIG_COUNT"] = str(n + 1)


AUDIT_TIMEOUT_S = 600          # one unmeasured compile per pin per candidate
AUDIT_MIN_PIN_S = 5            # no audit compile starts with less time than this before the audit deadline


def audit_proof(row: dict, proof: str, versions: list[str], seed_sorry: dict, audit=None, timeout: int = AUDIT_TIMEOUT_S,
                deadline: float | None = None) -> tuple[str, str]:
    """(clean | sorry | unknown | skipped, why) of one proof on every pin (section S): `sorry` when Lean's sorry message appears with
    warn.sorry forced on, or when sorryAx is among the declaration's axioms on a pin where the row's own seed does not depend on it
    (memoised in seed_sorry[version]); anything the audit cannot decide (exception, timeout, errors, no axiom output, no pin, the
    `deadline` reached) is `unknown`. Each compile's timeout is the smaller of `timeout` and the time left before `deadline`."""
    from scorer.compile import audit_axioms

    def tmo() -> int:
        return int(timeout if deadline is None else max(1, min(timeout, deadline - time.time())))
    aud = audit or (lambda r, p, v: audit_axioms(r, p, v, timeout=tmo()))
    if not versions:
        return "unknown", "the row lists no pin"
    unknown, skipped = [], []
    for v in versions:
        if deadline is not None and deadline - time.time() < AUDIT_MIN_PIN_S:
            unknown.append(f"{v}: the audit deadline was reached"); continue
        try:
            a = aud(row, proof, v)
        except Exception as e:  # noqa: BLE001
            unknown.append(f"{v}: {type(e).__name__}: {str(e)[:80]}"); continue
        c = getattr(a, "compile", None)
        if getattr(a, "switch", False) or getattr(a, "sorry_warning", False):
            return "sorry", f"axiom audit on {v}: the declaration uses sorry (warn.sorry forced on)"
        if c is not None and getattr(c, "timed_out", False):
            unknown.append(f"{v}: the audit compile timed out"); continue
        axs = getattr(a, "axioms", None)
        if axs is not None and "sorryAx" in axs:
            if v not in seed_sorry:
                try:
                    sa = aud(row, row["src"], v)
                    seed_sorry[v] = None if getattr(sa, "axioms", None) is None else ("sorryAx" in sa.axioms or bool(getattr(sa, "sorry_warning", False)))
                except Exception:  # noqa: BLE001
                    seed_sorry[v] = None
            if seed_sorry[v] is False:
                return "sorry", f"axiom audit on {v}: depends on sorryAx (the row's seed does not)"
            if not seed_sorry[v]:
                unknown.append(f"{v}: sorryAx without a sorry message and no seed verdict")
            continue
        if getattr(a, "decl_errors", None):
            unknown.append(f"{v}: the audit compile reports errors"); continue
        if getattr(a, "skipped", None):
            skipped.append(v); continue
        if axs is None:
            unknown.append(f"{v}: no #print axioms output"); continue
    if unknown:
        return "unknown", "; ".join(unknown)[:200]
    if skipped:
        return "skipped", f"sorry message check only on {', '.join(skipped)}; no sorry"
    return "clean", f"no sorry on {len(versions)} pin(s)"
