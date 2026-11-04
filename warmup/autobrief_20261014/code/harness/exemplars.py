#!/usr/bin/env python3
"""Exemplar transfer from the strongest rows (2026-10-13: rows at 90+ pass their practices on to the others,
like a training set; docs/cc_driver_v2.md §13). CPU only: no model call, no Lean.
The sharper version: transfer the TRANSFORMATIONS and the STYLE of the strong rows, not the rows, and aim at
heartbeats (the set #3 line has L ~81.7 but H ~70.3; its rows >= 90 reach H 84-93 on references of similar size):
  (1) jumps       every listed line's verified.jsonl histories (this line's run dirs; --extra-root lines with theirs): per (line, problem) the
                  consecutive best improvements from the reference on, with d_score / d_tokens / d_heartbeats and the tactic-family change. The
                  first change of the reference is included (the ledger keeps targeted edits only: discover, inrun.append_win); every jump is a
                  `rewrite` (its body diff touches > 60% of the lines) or an `edit`, the first one flagged; a record whose body equals the one
                  before is no jump; the reference's heartbeats are the local measurement (scorer.score, as H), else the official ones
  (2) style       per proof: tactic families per 100 tokens (FAMILIES: simp, simp only, simp_all, simpa, grind, grind only, omega, aesop, decide,
                  norm_num, linarith, exact?, rw, cases/induction, have/show/calc, first/try, all_goals/<;>, by-blocks), term mode and heartbeats per
                  token; a row below --target is compared with the rows >= --target of its own source (>= MIN_SAME of them, else of every
                  source) on the axis that holds its points (H, or L when L <= H - AXIS_MARGIN); listed are the families it uses more whose removal
                  saved that axis's measure WITHIN other problems: the median log change over their edits that removed the family against the
                  median over those that added it (review 2026-10-13: a cross-problem correlation with H measured sources and sizes, and
                  contradicted the edits), only families of this best's hot blocks when its profile is cached (else of its best)
  (2b) hot        HEARTBEAT HOT FAMILIES are computed when the prompt is built (exemplars_for), from the profile cached for the stored best's own
                  sha (the one the HEARTBEAT MAP shows, never another candidate's): its costliest leaf blocks with the families of the best's lines
  (3) retrieval   per row below --target the --top jumps of OTHER problems that saved its axis's measure: same source first, then entries with a
                  pattern (a mechanism or an `e.g.` line) before family changes alone, then the overlap of the families a jump removed with the
                  families this best uses (a bonus when they are its hot families), weighted by the jump's relative saving (and by 1.25 when its
                  row is now >= --target); one per problem, at most (top+1)//2 rewrites when an edit qualifies; rewrites of the reference only
                  for a row whose best is still near its reference (>= NEAR_REF of its tokens)
  (4) no proofs   rule for in-run cross-problem learning: general techniques, never proofs. A row never sees its own problem's data,
                  from any line. Entries are family names, counts and at most two abstracted lines per side (harness/transfer.py's abstraction:
                  identifiers of other rows as $A, $B; library names shared by >= 2 rows literal), only from proofs of >= SNIP_MIN_LINES tactic
                  lines (the `by` opener not counted), one entry per other problem (several could add up to its proof), each through
                  inrun.leak_lint over every listed line's rows (no Lean block > 2 lines, no problem name, no identifier of only one row); a
                  mechanism of a multi-place edit only from the place that removed one of the edit's removed families, labelled as one of N;
                  jumps only of problems with a workspace in their line (an identifier index for them)
<work root>/_exemplars/<ws dirname>.md (<= CAP chars; outside every workspace, so neither a session nor the reviewer reads it except through
the prompt: review 2026-10-13) of every work-root row below --target: a header with the stored best's sha, then STRONGEST ROWS STYLE and
RETRIEVED TRANSFORMATIONS; prompt v2 adds this best's HEARTBEAT HOT FAMILIES (agent_claude_code.py --exemplars). A row at or above --target gets
nothing (a stale file is removed; so is a <ws>/exemplars.md of the first version). Extra roots and run dirs of another sealed set or the A/B
pool are refused (transfer.set_tag, discover's rule); a missing extra root is counted, not fatal. stdout is counts only: row#k = index among
the work root's sorted workspaces, never a name.
    python3 harness/exemplars.py --work-root R [--runs-dir D ...] [--extra-root R2 [D2 ...]] [--target 90] [--top 3] [--dry-run]
"""
from __future__ import annotations

import argparse, collections, glob, json, math, re, statistics, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness import inrun  # noqa: E402
from harness import cc_levers as LV  # noqa: E402
from harness import transfer as T  # noqa: E402

FILE = "exemplars.md"  # the first version's <ws>/exemplars.md: never written now, removed when found
XDIR = "_exemplars"    # <work root>/_exemplars/<ws dirname>.md (transfer's _transfer/ precedent): outside every workspace
TAG = "<!-- lra-exemplars "
CAP = 1200             # the file at most, header included; the prompt adds the hot families (<= HOT_CAP): the block <= BLOCK_CAP
HOT_CAP, BLOCK_CAP = 300, 1500
TARGET, TOP = 90.0, 3
MIN_SAME = 2           # rows >= target of the row's own source needed for a same-source contrast; else every source
MIN_DEV = 0.5          # per 100 tokens: a smaller difference is no deviation
# a family's within-problem effect: >= MIN_N edits removed it, their median log change >= MIN_EFFECT[axis] below the reference (an edit moves
# tokens less than heartbeats: warm-up medians over 620 edits -0.9% hb, -1.7% tokens; removals of grind -35% hb, of have/show/calc -4.5% tokens)
MIN_N, MIN_EFFECT = 4, {"H": 0.07, "L": 0.02}
SHORT = 100            # a best under this many tokens: its family counts, not rates per 100 tokens
NEAR_REF = 0.5         # rewrites of the reference only for a row whose best keeps >= this share of its reference's tokens
AXIS_MARGIN = 5.0      # a row is on the L axis when its L is at least this far below its H
MAX_DEV, HOT_K, MAX_WILD = 4, 3, 4
SNIP_MIN_LINES = 3     # a pattern or snippet only from proofs of at least this many tactic lines: a fragment, never a whole proof
BASE, HOT_BONUS, STRONG_W = 0.25, 0.5, 1.25
FAMILIES = ("simp", "simp only", "simp_all", "simpa", "grind", "grind only", "omega", "aesop", "decide", "norm_num", "linarith", "exact?", "rw",
            "cases/induction", "have/show/calc", "first/try", "all_goals/<;>", "by")
_ONE = {"simp_all": "simp_all", "simpa": "simpa", "omega": "omega", "aesop": "aesop", "decide": "decide", "norm_num": "norm_num",
        "linarith": "linarith", "nlinarith": "linarith", "rw": "rw", "rwa": "rw", "rewrite": "rw", "erw": "rw", "nth_rewrite": "rw", "nth_rw": "rw",
        "simp_rw": "rw", "cases": "cases/induction", "cases'": "cases/induction", "induction": "cases/induction", "induction'": "cases/induction",
        "rcases": "cases/induction", "obtain": "cases/induction", "fun_induction": "cases/induction", "have": "have/show/calc",
        "haveI": "have/show/calc", "show": "have/show/calc", "calc": "have/show/calc", "suffices": "have/show/calc", "first": "first/try",
        "try": "first/try", "all_goals": "all_goals/<;>", "any_goals": "all_goals/<;>", "<;>": "all_goals/<;>", "by": "by"}
_HX = re.compile(r"-([rfp])(\d+)$")   # hx run ids: <prefix>-r<round> / -f<round> / -p<round>
# the words of this module's own templates: never from a proof, so the lint's plain-word rule does not apply to them (the code in backticks is
# linted again without them)
VOCAB = frozenset(("there", "here", "with", "over", "rows", "heartbeats", "token", "tokens", "median", "term", "mode", "tactic", "proof", "proofs",
                   "lines", "above", "floor", "total", "families", "family", "rewrite", "reference", "edit", "edits", "score", "that", "line",
                   "nothing", "delete", "inside", "place", "places", "changed", "goal", "last", "references", "same", "source", "application",
                   "lemma", "none", "change", "unchanged", "other", "problems", "removed", "added", "every", "points", "left", "length", "them",
                   "pattern", "what", "measured", "when", "they", "removing", "adding", "earlier", "best", "built", "numbers", "stored", "leaf",
                   "blocks", "closer"))


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read(p: Path):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


# ---- features -----------------------------------------------------------------------------------------------------------------------------
def families(text: str) -> collections.Counter:
    """Tactic-family counts of a proof text with the scorer's lexer (`_tokens`: its token count): `simp only` / `grind only` apart from bare
    `simp` / `grind`, `exact?` / `apply?`, and the families of _ONE."""
    from scorer.tokenize import tokens
    ts = tokens(text or ""); c: collections.Counter = collections.Counter(); c["_tokens"] = len(ts)
    for k, t in enumerate(ts):
        nxt = ts[k + 1] if k + 1 < len(ts) else ""
        if t in ("simp", "grind"):
            c[t + " only" if nxt == "only" else t] += 1
        elif t in ("exact", "apply") and nxt == "?":
            c["exact?"] += 1
        elif t in _ONE:
            c[_ONE[t]] += 1
    return c


def body_of(name: str, proof: str | None) -> str | None:
    """The proof body after the row's benchmark statement (scorer.tokenize.split_declaration), or None (no row, another statement)."""
    from harness.leantools import ROWS
    from scorer.tokenize import split_declaration
    row = ROWS.get(name)
    return split_declaration(proof.rstrip(), row["statement"]) if row and proof else None


def features(body: str, heartbeats=None) -> dict | None:
    """Family counts and rates per 100 tokens, tokens, heartbeats per token, term mode (the body does not open a `by` block)."""
    c = families(body); n = c["_tokens"]
    if not n:
        return None
    return {"counts": c, "rates": {f: round(c[f] * 100.0 / n, 2) for f in FAMILIES}, "tokens": n,
            "hb_tok": float(heartbeats) / n if heartbeats else None, "term": not body.strip().startswith("by")}


def nonblank(text: str) -> int:
    return sum(1 for l in (text or "").split("\n") if l.split("--", 1)[0].strip())


def tactic_lines(body: str) -> int:
    """Non-blank lines of a proof body without its `by` opener (review 2026-10-13: ` by` alone is no tactic line, so a 2-tactic proof counted 3)."""
    return nonblank(re.sub(r"^\s*by\b", "", body or "", count=1))


# ---- the lines: rows and jumps ----------------------------------------------------------------------------------------------------------
def _natural(s: str) -> list:
    return [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", s)]


def expand(specs) -> tuple[list[Path], int]:
    """Run directories from paths or globs (relative to the checkout, or absolute), (dirs, missing). A glob is in check order: when every hit
    is an hx run id (-r<k> / -f<k> / -p<k>), by round, then resume / fresh / polish (hx line_runs; review 2026-10-13: in natural order every
    fresh lineage sorted before every resume), else natural order (p2 before p10)."""
    out: list = []; miss = 0
    for s in specs:
        p = str(ROOT / s)
        if re.search(r"[*?\[]", s):
            hits = sorted(glob.glob(p), key=_natural)
            ms = [_HX.search(Path(h).name) for h in hits]
            if hits and all(ms):
                hits = [h for _m, h in sorted(zip(ms, hits), key=lambda x: (int(x[0].group(2)), "rfp".index(x[0].group(1))))]
        else:
            hits = [p]
        hits = [Path(h) for h in hits if Path(h).is_dir()]
        miss += not hits
        out += [h for h in hits if h not in out]
    return out, miss


def records(run_dirs) -> tuple[dict, int]:
    """verified.jsonl records per problem, run dirs in the given order and each file in its order (check order)."""
    by: dict = collections.defaultdict(list); n = 0
    for d in run_dirs:
        try:
            lines = (Path(d) / "verified.jsonl").read_text().splitlines()
        except OSError:
            continue
        for l in lines:
            try:
                j = json.loads(l)
            except ValueError:
                continue
            if isinstance(j, dict) and j.get("problem") and j.get("proof") and j.get("score") is not None:
                by[j["problem"]].append(j); n += 1
    return by, n


def ref_heartbeats(name: str) -> int | None:
    """The reference's heartbeats on H's scale: the local measurement (scorer.score.local_reference_heartbeats), else the official one."""
    from harness.leantools import HBS
    from scorer.score import local_reference_heartbeats
    return local_reference_heartbeats(name) or HBS.get(name)


def chain(name: str, recs: list, line: int, strong: bool) -> list[dict]:
    """The consecutive best improvements of one line on one problem from the reference on (discover's chain). Each is a `rewrite` when its body
    diff touches > 60% of the lines, else an `edit`; the first change of the reference is flagged first=True (review 2026-10-13: it was always
    a rewrite, even a 1-hunk edit). A better record with the same body (a remeasurement) moves the numbers on but is no jump."""
    from harness.leantools import ROWS
    from harness.discover import diff
    row = ROWS[name]; prev = {"score": 33.33, "tokens": row["proof_length"], "heartbeats": ref_heartbeats(name)}
    pb = body_of(name, row["src"]) or row["src"]; out = []
    for j in recs:
        try:
            sc = float(j["score"])
        except (TypeError, ValueError):
            continue
        b = body_of(name, j["proof"])
        if b is None or sc <= float(prev["score"]) + 1e-9:
            continue
        d = diff(pb, b)
        if not d:
            prev = j; continue
        hb0, hb1 = prev.get("heartbeats"), j.get("heartbeats"); t0 = int(prev.get("tokens") or 0)
        out.append({"line": line, "problem": name, "source": row["source"], "first": not out,
                    "kind": "rewrite" if len(d) > 0.6 * (len(pb.splitlines()) + len(b.splitlines())) else "edit",
                    "d_score": round(sc - float(prev["score"]), 2), "d_tok": int(j.get("tokens") or 0) - t0, "tok_before": t0,
                    "d_hb": int(hb1) - int(hb0) if hb0 is not None and hb1 is not None else None, "hb_before": hb0,
                    "before": families(pb), "after": families(b), "old": pb, "new": b, "diff": d, "strong": strong})
        prev, pb = j, b
    return out


# ---- the leak index ---------------------------------------------------------------------------------------------------------------------
class Index:
    """inrun's leak-lint index over every listed line's rows (original.lean + context.lean per problem) and every known problem name."""

    def __init__(self, files: dict, names):
        from harness.leantools import ROWS
        self.owner, self.declared = inrun.ident_index(files), inrun.declared_names(files)
        self.terms = inrun.name_terms(sorted(set(names) | set(ROWS)), ROWS)
        self.safe = inrun._tactics() | inrun.KEEP_WORDS | VOCAB | {r.get("source") for r in ROWS.values() if r.get("source")}   # + source tags
        self.rejected = 0

    def ok(self, text: str) -> bool:
        """The entry passes inrun.leak_lint (the template's words allowed), and its code in backticks passes it without them."""
        code = " ".join(re.findall(r"`([^`]*)`", text))
        good = (inrun.leak_lint(text, self.terms, self.owner, self.safe, self.declared) is None
                and (not code.strip() or inrun.leak_lint(code, self.terms, self.owner, None, self.declared) is None))
        self.rejected += not good
        return good


# ---- (2) style contrast ---------------------------------------------------------------------------------------------------------------
def _k(x) -> str:
    return f"{x / 1000:.1f}k" if x and x >= 1000 else f"{x}"


def _pct(x: float) -> str:
    return f"{100 * (math.exp(x) - 1):+.0f}%"


def axis_of(H, L) -> str:
    """The axis that holds a best's points (review 2026-10-13: an L-weak row got heartbeat-only content): 'L' when its L is at least
    AXIS_MARGIN below its H, else 'H' (near-ties stay on heartbeats, the chosen emphasis)."""
    return "L" if H is not None and L is not None and float(L) <= float(H) - AXIS_MARGIN else "H"


def effects(jumps: list, problem: str, axis: str) -> tuple[dict, list]:
    """Within-problem evidence (review 2026-10-13): the log change of the axis's measure (heartbeats; tokens for an L row) over the edits of
    OTHER problems, per family over those that removed it and those that added it, and over every such edit. ({family: (removed, added)},
    every)."""
    rm, add, every = collections.defaultdict(list), collections.defaultdict(list), []
    for j in jumps:
        if j["problem"] == problem or j["kind"] != "edit":
            continue
        b, d = (j.get("hb_before"), j.get("d_hb")) if axis == "H" else (j.get("tok_before"), j.get("d_tok"))
        if not b or d is None or b + d <= 0:
            continue
        x = math.log((b + d) / b); every.append(x)
        for f in FAMILIES:
            if f != "by" and j["after"][f] != j["before"][f]:
                (rm if j["after"][f] < j["before"][f] else add)[f].append(x)
    return {f: (rm[f], add[f]) for f in FAMILIES}, every


def contrast(t: dict, strong: list, target: float, eff: tuple, hot: set) -> tuple[list, str, int]:
    """STRONGEST ROWS STYLE lines of row t on its axis (t['axis']): the context line (the pool's H, or L, and reference sizes against this
    row's), heartbeats per token (H), and the families t uses more than the rows >= target of its source (MIN_SAME of them, else every source;
    never t's own problem from any line) whose removal saved the axis's measure in other problems' edits (`eff`, effects()): >= MIN_N edits
    removed it, their median log change >= MIN_EFFECT[axis] below the median of the edits that added it (of every edit when < MIN_N added it).
    Candidates: the families of t's hot blocks when its profile is cached (`hot`), else of its best; counts, not rates, for a best under
    SHORT tokens. The term-mode line last. Returns (lines, scope, pool size)."""
    pool = [r for r in strong if r["problem"] != t["problem"]]
    same = [r for r in pool if r["source"] == t["source"]]
    use, scope = (same, "of this source") if len(same) >= MIN_SAME else (pool, "of every source")
    if not use:
        return [], scope, 0
    ax = t.get("axis", "H"); out = []
    if ax == "H":
        hs = [r["H"] for r in use if r.get("H") is not None]; refs = [r["ref_hb"] for r in use if r.get("ref_hb")]
        if hs and refs and t.get("H") is not None:
            out.append(f"- H {min(hs):.0f}-{max(hs):.0f} there on references of {_k(min(refs))}-{_k(max(refs))} hb; here H {t['H']:.1f} on "
                       f"{_k(t.get('ref_hb'))} hb")
        ht = [r["f"]["hb_tok"] for r in use if r["f"]["hb_tok"]]
        if ht and t["f"]["hb_tok"]:
            out.append(f"- heartbeats per token: median {statistics.median(ht):.1f} there vs {t['f']['hb_tok']:.1f} here")
    else:
        ls = [r["L"] for r in use if r.get("L") is not None]; refs = [r["ref_tok"] for r in use if r.get("ref_tok")]
        if ls and refs and t.get("L") is not None:
            out.append(f"- L {min(ls):.0f}-{max(ls):.0f} there on references of {min(refs)}-{max(refs)} tokens; here L {t['L']:.1f} on "
                       f"{t.get('ref_tok')} tokens")
    per, every = eff; base = statistics.median(every) if every else None
    unit = "hb" if ax == "H" else "tokens"; n_tok = t["f"]["tokens"]; short = n_tok < SHORT
    cand = set(hot) if hot else {f for f in FAMILIES if t["f"]["counts"][f]}
    devs = []
    for f in FAMILIES:
        if f == "by" or f not in cand:
            continue
        here, c = t["f"]["rates"][f], t["f"]["counts"][f]; there = statistics.mean(r["f"]["rates"][f] for r in use)
        if here - there < MIN_DEV or (short and c - there * n_tok / 100.0 < 1):
            continue
        rm, add = per.get(f, ([], []))
        if len(rm) < MIN_N:
            continue
        m = statistics.median(rm)
        if len(add) >= MIN_N:
            ref = statistics.median(add); why = f"that added it: {_pct(ref)} over {len(add)}"
        elif base is not None:
            ref = base; why = f"every edit: {_pct(base)} over {len(every)}"
        else:
            continue
        if m - ref > -MIN_EFFECT[ax]:
            continue
        has = f"{c} here in {n_tok} tokens vs {there:.1f} per 100 tokens there" if short else f"{there:.1f} there vs {here:.1f} here per 100 tokens"
        devs.append((m - ref, FAMILIES.index(f), f"- {f}: {has}; other problems' edits that removed it: median {_pct(m)} {unit} over {len(rm)} ({why})"))
    out += [x for *_k_, x in sorted(devs)[:MAX_DEV]]
    nt = sum(r["f"]["term"] for r in use)
    if (nt * 2 >= len(use)) != bool(t["f"]["term"]):
        out.append(f"- term mode: {nt} of {len(use)} there vs " + ("a term proof here" if t["f"]["term"] else "a tactic proof here"))
    return out, scope, len(use)


def hot_families(state: dict, proof: str | None) -> tuple[list, set, str | None]:
    """HEARTBEAT HOT FAMILIES of the stored best `proof`: from the heartbeat profile cached for ITS sha only (review 2026-10-13: never another
    candidate's, whose line ranges point elsewhere in this best), the HOT_K costliest LEAF blocks (a block containing another profiled block is
    left out, so the shares never add up past 100%), each with its share above the floor and the families of the best's own lines in its range
    (not profile.py's 100-char excerpt). Block text never leaves this function: line ranges, numbers, families."""
    prof = (state.get("profile_cache") or {}).get(LV.proof_sha(proof)) if proof else None
    if not isinstance(prof, dict) or not prof.get("ok") or not prof.get("blocks"):
        return [], set(), None
    bl = []
    for b in prof["blocks"]:
        m = re.fullmatch(r"(\d+)-(\d+)", str(b.get("lines") or "")) if isinstance(b, dict) else None
        if m and (b.get("heartbeats") or 0) > 0:
            bl.append((int(m.group(1)), int(m.group(2)), b))
    leaves = [x for x in bl if not any(o[:2] != x[:2] and x[0] <= o[0] and o[1] <= x[1] for o in bl)]
    src = proof.rstrip().split("\n"); above = (prof.get("total") or 0) - (prof.get("floor") or 0); out, hot = [], set()
    for a, z, b in sorted(leaves, key=lambda x: -x[2]["heartbeats"])[:HOT_K]:
        c = families("\n".join(src[a - 1:z])); fams = [f for f in FAMILIES if c[f] and f != "by"]
        hot |= set(fams)
        out.append(f"- lines {a}-{z}: {b['heartbeats']} hb" + (f" ({round(100 * b['heartbeats'] / above)}% above the floor)" if above > 0 else "")
                   + ": " + (", ".join(fams) if fams else "no closer family (a term or a lemma application)"))
    head = (f"HEARTBEAT HOT FAMILIES (heartbeat_profile of the stored best, best.lean lines, leaf blocks: total {prof.get('total')} hb, "
            f"floor {prof.get('floor')} hb):")
    return out, hot, head


def hot_section(state: dict, proof: str | None) -> str:
    """hot_families() as text within HOT_CAP (blocks dropped from the last), "" without a profile of this best."""
    lines, _hot, head = hot_families(state, proof)
    while lines and len("\n".join([head] + lines)) > HOT_CAP:
        lines.pop()
    return "\n".join([head] + lines) if lines else ""


# ---- (3) retrieval and (4) abstraction --------------------------------------------------------------------------------------------------
def fam_delta(j: dict, k: int = 4) -> str:
    """The k largest family changes of a jump, `family before->after`; at equal size the removed families first."""
    ch = [(abs(j["after"][f] - j["before"][f]), j["after"][f] > j["before"][f], FAMILIES.index(f), f) for f in FAMILIES
          if j["after"][f] != j["before"][f] and f != "by"]
    return ", ".join(f"{f} {j['before'][f]}->{j['after'][f]}" for *_k, f in sorted(ch, key=lambda x: (-x[0], x[1], x[2]))[:k])


def mechanisms(gs: list, owner: dict) -> list[dict]:
    """transfer.py's mechanisms of (old lines, new lines) groups of a body diff, group by group (a group of 700+ chars gives none: transfer's
    cut-diff rule)."""
    out = []
    for old, new in gs:
        g = "\n".join(["-" + l for l in old] + ["+" + l for l in new])
        if len(g) < T.DIFF_CAP:
            out += T.mine_win({"diff": g, "kind": "edit"}, owner)
    return out


def _mech_key(m: dict) -> tuple:
    old = "\n".join(T.show(x) for x in m.get("old") or []); new = "\n".join(T.show(x) for x in m.get("new") or [])
    fo, fn = families(old), families(new)
    return (all(fo[f] == fn[f] for f in FAMILIES), len(m.get("old") or []) + len(m.get("new") or []) > 2, ("rule", "span", "delete").index(m["kind"]))


def snippet(line: str, owner: dict, cap: int = 90) -> str | None:
    """One line abstracted as transfer's closers: every identifier that is not a keyword or a shared name becomes $A, $B (at most MAX_WILD);
    None for an unbalanced line (a piece of a term), too many wildcards or a long line."""
    s = line.split("--", 1)[0].strip(); toks = T.lex(s); kw = T.keywords(); names: dict = {}
    for k, t, *_ in toks:
        if k == "id" and t not in kw and not T.shared_name(t, owner):
            names.setdefault(t, len(names))
    if not toks or len(names) > MAX_WILD or any(T._balance([toks])):
        return None
    out = T.show(T._template(s, toks, names))
    return out if len(out) <= cap else None


def _place(j: dict, owner: dict) -> tuple[list, str]:
    """The diff groups an edit's mechanism may come from, and the label. One changed place: it. Several (review 2026-10-13: the shown hunk was
    often an incidental one): only the place that removed the most of the families the whole edit removed, labelled `at 1 of N changed
    places`; none when no place removed one of them."""
    gs = T.groups("\n".join(j["diff"]))
    if len(gs) <= 1:
        return gs, ""
    removed = {f for f in FAMILIES if f != "by" and j["before"][f] > j["after"][f]}
    ranked = []
    for g in gs:
        fo, fn = families("\n".join(g[0])), families("\n".join(g[1]))
        w = sum(fo[f] - fn[f] for f in removed if fo[f] > fn[f])
        if w > 0:
            ranked.append((-w, len(ranked), g))
    return [min(ranked)[2]] if ranked else [], f"at 1 of {len(gs)} changed places, "


def describe(j: dict, idx: Index, target: float, axis: str = "H") -> list[str]:
    """The entry texts of one jump, most informative first, each passing the leak lint: [tag] numbers (the axis's own first): a transfer
    mechanism of an edit (`old` -> `new`, abstracted; of a multi-place edit only the place that removed its removed families) or the family
    change with one abstracted line of the new proof (`e.g.`); then the family change alone. Patterns and snippets only from proofs of >=
    SNIP_MIN_LINES tactic lines on both sides, so they are fragments, never a whole proof. [] when nothing passes."""
    if axis == "H":
        pct = f" ({round(100 * j['d_hb'] / j['hb_before'])}%)" if j.get("hb_before") else ""
        nums = f"{j['d_hb']:+d} hb{pct}, {j['d_score']:+.2f} score, {j['d_tok']:+d} tok"
    else:
        pct = f" ({round(100 * j['d_tok'] / j['tok_before'])}%)" if j.get("tok_before") else ""
        nums = f"{j['d_tok']:+d} tok{pct}, {j['d_score']:+.2f} score, {j['d_hb']:+d} hb"
    kind = (f"{j['kind']} of the reference" if j["first"] else j["kind"])
    tag = f"[{j['source']}; {kind}" + (f"; that row is now >= {target:g}" if j["strong"] else "") + "]"
    head = f"{tag} {nums}"
    fam = fam_delta(j); out = []
    frag = tactic_lines(j["new"]) >= SNIP_MIN_LINES and tactic_lines(j["old"]) >= SNIP_MIN_LINES
    if frag and j["kind"] == "edit":
        gs, where = _place(j, idx.owner)
        ms = mechanisms(gs, idx.owner)
        if ms:
            out.append(f"{head}: {where}{T.describe(min(ms, key=_mech_key))}" + (f" ({fam})" if fam else ""))
    if frag and fam:
        inc = [f for f in FAMILIES if j["after"][f] > j["before"][f] and f != "by"]
        for l in j["new"].split("\n"):
            c = families(l)
            if any(c[f] for f in inc):
                s = snippet(l, idx.owner)
                if s:
                    out.append(f"{head}: {fam}; e.g. `{s}`"); break
    if fam:
        out.append(f"{head}: {fam}")
    return [x for x in out if idx.ok(x)]


def retrieve(t: dict, jumps: list, hot: set, top: int, target: float, idx: Index, cache: dict) -> list[dict]:
    """The `top` jumps of other problems that saved row t's axis (t['axis']; H: d_heartbeats < 0; L: d_tokens < 0 at no heartbeat cost):
    same source first; then entries with a pattern (a mechanism or an `e.g.` line) before family changes alone (review 2026-10-13); then
    relevance = (BASE + the share of the families the jump removed that t's best uses + HOT_BONUS when one of them is hot here; `by` is no
    family here) x the jump's relative saving (x STRONG_W when its row is now >= target). One per problem, from any line and in every pass
    (several entries of one problem could add up to its proof); at most (top+1)//2 rewrites while an edit qualifies (a last pass lifts that
    cap); rewrites of the reference only for a row whose best keeps >= NEAR_REF of its reference's tokens; a jump whose entries all fail the
    lint is no candidate. Each pick: {'j', 'same', 'texts'}."""
    ax = t.get("axis", "H"); used = {f for f in FAMILIES if f != "by" and t["f"]["counts"][f] > 0}
    near = t["f"]["tokens"] >= NEAR_REF * (t.get("ref_tok") or 0); cands = []
    for j in jumps:
        if j["problem"] == t["problem"] or j["d_hb"] is None or j["d_score"] <= 0:
            continue
        if ax == "H":
            if j["d_hb"] >= 0:
                continue
            frac = min(1.0, -j["d_hb"] / max(1, j["hb_before"] or 1))
        else:
            if j["d_tok"] >= 0 or j["d_hb"] > 0:
                continue
            frac = min(1.0, -j["d_tok"] / max(1, j.get("tok_before") or 1))
        if j["first"] and j["kind"] == "rewrite" and not near:
            continue
        dec = {f for f in FAMILIES if f != "by" and j["before"][f] > j["after"][f]}
        overlap = len(dec & used) / len(dec) if dec else 0.0
        rel = (BASE + overlap + (HOT_BONUS if dec & hot else 0.0)) * frac * (STRONG_W if j["strong"] else 1.0)
        key = (id(j), ax)
        if key not in cache:
            cache[key] = describe(j, idx, target, ax)
        if cache[key]:
            cands.append((j["source"] == t["source"], any("`" in x for x in cache[key]), rel, j))
    cands.sort(key=lambda c: (-c[0], -c[1], -c[2], -c[3]["d_score"]))
    max_rw = (top + 1) // 2 if any(c[3]["kind"] == "edit" for c in cands) else top
    pick, probs = [], set()
    for cap in (max_rw, top):
        for same, _pat, _rel, j in cands:
            if len(pick) >= top:
                return pick
            texts = cache[(id(j), ax)]
            if (j["problem"] in probs or (j["kind"] != "edit" and sum(p["j"]["kind"] != "edit" for p in pick) >= cap)
                    or texts[0] in {p["texts"][0] for p in pick}):
                continue
            pick.append({"j": j, "same": same, "texts": texts}); probs.add(j["problem"])
    return pick


# ---- the file -------------------------------------------------------------------------------------------------------------------------------
def path_for(ws_root) -> Path:
    """<work root>/_exemplars/<ws dirname>.md: outside the workspace (a session reads its workspace; the reviewer has Read on it)."""
    ws = Path(ws_root)
    return ws.parent / XDIR / f"{ws.name}.md"


def header(sha: str, t: str, target: float, strong: int, k: int, axis: str = "H") -> str:
    return f"{TAG}best_sha={sha} t={t} target={target:g} axis={axis} strong={strong} transformations={k} -->"


def parse(text: str) -> tuple[dict, str] | None:
    """(header fields, body) of an exemplars file, or None when its first line is not an exemplars header."""
    head, _, body = (text or "").partition("\n")
    if not head.startswith(TAG):
        return None
    return dict(re.findall(r"(\w+)=(\S+)", head[len(TAG):].replace("-->", ""))), body.strip()


def exemplars_for(ws_root, state: dict) -> tuple[str, str, bool] | None:
    """(block text, the sha the file was built for, stale) of the workspace's exemplars file for its stored best; None without a file or a
    best, or once the best reached the file's target. The text is the file's body with this best's HEARTBEAT HOT FAMILIES (hot_section, from
    the profile cached NOW: the one the HEARTBEAT MAP shows) before RETRIEVED TRANSFORMATIONS, cut at BLOCK_CAP on a line boundary. A file built
    for an earlier best of this workspace (stale: e.g. a transfer-lane hit since the last build; review 2026-10-13) is shown with a line saying
    so: its style and retrieval are about other problems; only its 'here' numbers are the earlier best's."""
    try:
        parsed = parse(path_for(ws_root).read_text())
    except OSError:
        return None
    best = state.get("best") or {}; proof = best.get("proof")
    if not parsed or not proof or not parsed[1]:
        return None
    meta, body = parsed
    try:
        if float(best.get("score") or 33.33) >= float(meta.get("target", TARGET)):
            return None
    except ValueError:
        return None
    sha = meta.get("best_sha") or "?"; stale = sha != LV.proof_sha(proof)
    L = body.split("\n"); hot = hot_section(state, proof)
    if hot:
        k = next((i for i, l in enumerate(L) if l.startswith("RETRIEVED TRANSFORMATIONS")), len(L))
        L[k:k] = hot.split("\n")
    if stale:
        L.insert(0, f"(built for an earlier best of this problem, sha {sha}: the style lines' 'here' numbers are that best's)")
    text = "\n".join(L)
    if len(text) > BLOCK_CAP:
        text = text[:BLOCK_CAP]; text = text[:text.rfind("\n")]
    return text, sha, stale


def assemble(head: str, style: list, scope: str, n: int, target: float, axis: str, picks: list, var: list) -> str:
    L = [head]
    if style:
        L += [f"STRONGEST ROWS STYLE ({n} row(s) >= {target:g} {scope}, other problems; the points left here are in "
              f"{'heartbeats' if axis == 'H' else 'length'}; families there vs here, with what other problems' edits measured when they removed "
              "one):"] + style
    if picks:
        L.append(f"RETRIEVED TRANSFORMATIONS (measured on other problems' bests: {'d_heartbeats' if axis == 'H' else 'd_tokens'}, d_score, "
                 f"{'d_tokens' if axis == 'H' else 'd_heartbeats'}; abstract patterns, $A/$B = names of your own proof, not proofs):")
        L += [f"{k}. {p['texts'][min(var[k - 1], len(p['texts']) - 1)]}" for k, p in enumerate(picks, 1)]
    return "\n".join(L)


def compose(t: dict, strong: list, jumps: list, idx: Index, target: float, top: int, cache: dict, t_iso: str) -> tuple[str | None, dict]:
    """The exemplars file of row t (None when neither section has content), fitted under CAP: first the shorter variant of the longest
    transformation, then style lines beyond 2, transformations from the last; the last resort is a cut at a line boundary. The hot families
    of a profile of this very best (if cached now) steer the style candidates and the retrieval bonus; the prompt shows them (exemplars_for)."""
    _hl, hset, _hh = hot_families(t["state"], t.get("proof"))
    ek = ("eff", t["problem"], t["axis"])
    if ek not in cache:
        cache[ek] = effects(jumps, t["problem"], t["axis"])
    style, scope, n = contrast(t, strong, target, cache[ek], hset)
    picks = retrieve(t, jumps, hset, top, target, idx, cache)
    if not style and not picks:
        return None, {}
    var = [0] * len(picks)
    while True:
        text = assemble(header(t["sha"], t_iso, target, n, len(picks), t["axis"]), style, scope, n, target, t["axis"], picks, var)
        if len(text) <= CAP:
            break
        longer = [k for k, p in enumerate(picks) if var[k] < len(p["texts"]) - 1]
        if longer:
            k = max(longer, key=lambda k: len(picks[k]["texts"][var[k]])); var[k] += 1
        elif len(style) > 2:
            style.pop()
        elif picks:
            picks.pop(); var.pop()
        else:
            text = text[:CAP]; text = text[:text.rfind("\n")]; break
    return text, {"style": len(style), "hot": len(_hl), "picks": len(picks), "same": sum(p["same"] for p in picks),
                  "first": sum(p["j"]["first"] for p in picks), "chars": len(text), "pool": n, "axis": t["axis"]}


def _unlink(fp: Path, write: bool, c: collections.Counter, key: str = "removed") -> None:
    if fp.exists():
        c[key] += 1
        if write:
            fp.unlink()


def build(work_root, runs=(), extras=(), target: float = TARGET, top: int = TOP, write: bool = True, t_iso: str | None = None,
          texts: dict | None = None) -> dict:
    """Every work-root row below `target` gets <work root>/_exemplars/<ws>.md (write=False: nothing written). runs: this line's run dirs;
    extras: (root, run dirs) of other lines (a missing root is counted and skipped; one of another sealed set is refused); texts: when a dict,
    each row's file text by its row#k index (tests, dry-run inspection). Returns {'c': counts, 'rows': per-row counts-only lines}."""
    from harness.leantools import ROWS, HBS
    wr = Path(work_root); tag = T.set_tag(wr); t_iso = t_iso or _now()
    lines, seen = [(wr, list(runs))], {wr.resolve()}
    for r, ds in extras:
        if Path(r).resolve() not in seen:
            seen.add(Path(r).resolve()); lines.append((Path(r), list(ds)))
    for r, ds in lines:   # discover's / transfer's rule: never another sealed set or the A/B pool into this set's line
        for x in [r, *ds]:
            if T.set_tag(x) and T.set_tag(x) != tag:
                raise ValueError(f"a root or run dir of set {T.set_tag(x)} refused for a work root of {'set ' + tag if tag else 'no sealed set'}")
    c: collections.Counter = collections.Counter(); keep = []
    for k, (r, ds) in enumerate(lines):
        if k and not r.is_dir():   # review 2026-10-13: one bad extra made every after-batch build exit 2 (a ladder silently without exemplars)
            c["extra_missing"] += 1; continue
        keep.append((r, ds))
    lines = keep; c.update(lines=len(lines), runs=sum(len(ds) for _r, ds in lines)); per = []; names = set()
    files: dict = {}
    for k, (r, ds) in enumerate(lines):
        ws = T.workspaces(r); per.append(ws)
        for w in ws:
            names.add(w["problem"]); files.setdefault(w["problem"], [w["dir"] / "original.lean", w["dir"] / "context.lean"])
    rows, jumps = [], []
    for k, (r, ds) in enumerate(lines):
        mine = {}
        for w in per[k]:
            s = w["state"] or {}; b = s.get("best") or {}
            f = features(body_of(w["problem"], b.get("proof")) or "", b.get("heartbeats")) if w["problem"] in ROWS and b.get("proof") else None
            if f is None:
                c["no_best" if k == 0 else "extra_no_best"] += 1; continue
            H = float(b["H"]) if b.get("H") is not None else None; L = float(b["L"]) if b.get("L") is not None else None
            row = {"line": k, "i": w["i"], "dir": w["dir"], "problem": w["problem"], "source": ROWS[w["problem"]]["source"], "state": s,
                   "score": float(b.get("score") or 33.33), "H": H, "L": L, "axis": axis_of(H, L), "ref_hb": HBS.get(w["problem"]),
                   "ref_tok": ROWS[w["problem"]].get("proof_length"), "f": f, "proof": b["proof"], "sha": LV.proof_sha(b["proof"])}
            rows.append(row); mine[w["problem"]] = row
        if k:
            c["extra_rows"] += len(mine); c["extra_empty"] += not mine
        recs, n = records(ds); c["records"] += n; names |= set(recs)
        for name, rs in recs.items():
            if name not in mine:   # only problems with a workspace in this line: the identifier index knows their files
                c["records_skipped"] += len(rs); continue
            jumps += chain(name, rs, k, mine[name]["score"] >= target)
    idx = Index(files, names)
    strong = [r for r in rows if r["score"] >= target]
    c.update(jumps=len(jumps), first=sum(j["first"] for j in jumps), first_rewrites=sum(j["first"] and j["kind"] == "rewrite" for j in jumps),
             rewrites=sum(j["kind"] == "rewrite" and not j["first"] for j in jumps), edits=sum(j["kind"] == "edit" for j in jumps),
             hb_saving=sum(j["d_hb"] is not None and j["d_hb"] < 0 for j in jumps), strong=len(strong))
    out, cache = [], {}
    for t in [r for r in rows if r["line"] == 0]:
        fp = path_for(t["dir"]); c["rows"] += 1
        _unlink(t["dir"] / FILE, write, c, "legacy_removed")   # the first version wrote <ws>/exemplars.md: a session could read it
        if t["score"] >= target:
            c["at_target"] += 1; _unlink(fp, write, c); continue
        c["below"] += 1; c["axis_L"] += t["axis"] == "L"
        text, st = compose(t, strong, jumps, idx, target, top, cache, t_iso)
        if text is None:
            c["empty"] += 1; _unlink(fp, write, c); continue
        if write:
            fp.parent.mkdir(exist_ok=True)
            tmp = fp.with_name(f".{fp.name}.tmp"); tmp.write_text(text + "\n"); tmp.replace(fp)
        if texts is not None:
            texts[t["i"]] = text
        c["written"] += 1
        out.append(f"row#{t['i']}: axis {st['axis']}, {st['style']} style line(s) against {st['pool']} row(s) >= {target:g}, {st['hot']} hot "
                   f"block(s) cached, {st['picks']} transformation(s) ({st['same']} same source, {st['first']} first change(s) of the reference), "
                   f"{st['chars']} chars")
    c["lint_rejected"] = idx.rejected
    return {"c": c, "rows": out}


def summary(c: collections.Counter, target: float, dry: bool, missing: int = 0) -> str:
    ex = (f"; extra line(s): {c['extra_rows']} row(s), {c['extra_no_best']} without a best or row, {c['extra_empty']} line(s) with no row, "
          f"{c['extra_missing']} root(s) missing" if c["extra_rows"] or c["extra_no_best"] or c["extra_empty"] or c["extra_missing"] else "")
    return (f"exemplars{' dry run' if dry else ''}: {c['rows']} row(s) in the work root ({c['at_target']} >= {target:g}: nothing, {c['below']} below "
            f"({c['axis_L']} on the L axis), {c['no_best']} without a best or row); {c['lines']} line(s), {c['runs']} run dir(s)"
            + (f" ({missing} missing)" if missing else "")
            + f", {c['records']} record(s) ({c['records_skipped']} of problems without a workspace) -> {c['jumps']} jump(s) ({c['first']} first "
            f"change(s) of the reference, {c['first_rewrites']} of them rewrites; {c['rewrites']} later rewrite(s), {c['edits']} edit(s); "
            f"{c['hb_saving']} heartbeat-saving){ex}; {c['strong']} row(s) >= {target:g} across the lines; {c['written']} exemplars file(s) "
            f"{'to write' if dry else 'written'}, {c['empty']} with nothing to show, {c['removed']} stale {'to remove' if dry else 'removed'}"
            + (f", {c['legacy_removed']} <ws>/{FILE} {'to remove' if dry else 'removed'}" if c["legacy_removed"] else "")
            + f"; {c['lint_rejected']} entr(y/ies) dropped by the leak lint")


def main() -> int:
    ap = argparse.ArgumentParser(description="exemplar transfer from the strongest rows (docs/cc_driver_v2.md §13)")
    ap.add_argument("--work-root", required=True, help="the line's work root (relative to the checkout, or absolute)")
    ap.add_argument("--runs-dir", nargs="+", action="append", default=[], metavar="DIR", help="this line's run directories (each with a "
                    "verified.jsonl; globs allowed: hx run ids in round order, else natural order), oldest first")
    ap.add_argument("--extra-root", nargs="+", action="append", default=[], metavar="R", help="another line on the same set: its work root, then "
                    "its run directories (R [DIR ...]); repeatable; a missing root is counted in the summary, not fatal")
    ap.add_argument("--target", type=float, default=TARGET, help="rows at or above this score are the strongest rows and get nothing")
    ap.add_argument("--top", type=int, default=TOP, help="retrieved transformations per row")
    ap.add_argument("--dry-run", action="store_true", help="build everything, write nothing (counts only)")
    a = ap.parse_args()
    root = ROOT / a.work_root
    if not root.is_dir():
        ap.error("--work-root is not a directory")
    runs, miss = expand([x for g in a.runs_dir for x in g]); extras = []
    for g in a.extra_root:
        ds, m = expand(g[1:]); miss += m; extras.append((ROOT / g[0], ds))
    try:
        res = build(root, runs, extras, a.target, max(1, a.top), write=not a.dry_run)
    except ValueError as e:
        ap.error(str(e))
    for line in res["rows"]:   # per-row lines first: the ladder log keeps the last lines of a post-batch step (the summary)
        print(line)
    print(summary(res["c"], a.target, a.dry_run, miss))
    if res["c"]["extra_missing"] or res["c"]["extra_empty"]:
        print(f"exemplars WARNING: {res['c']['extra_missing']} extra root(s) missing, {res['c']['extra_empty']} extra line(s) with no row "
              "(nothing from them)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
