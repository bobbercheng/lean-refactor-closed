#!/usr/bin/env python3
"""T11 relation template (b63, docs/adaptive_plan_93.md §4.1 item 11; B §3 "extracted" row, T10 pretest, this family build): a goal-keyed
WHOLE-PROOF template built from the relation table (harness/tools/tables/relations.json, gen_relations.py: strengthenings R' ⇒ R,
congruences of a relation over constructors, reflexivity and least elements, all read off lemma TYPES) and the closer table
(harness/tools/tables/closers.json, gen_closers.py: argument-free tactics and the synthetic goals each closes), screened on the workbench,
handed to the end stage as compiled candidates (the t5 contract: search() on the workbench, candidates() from ctx["t11_found"], explain()
without Lean), and, when no candidate closes, as NEAR-MISSES (the template text with its open goals as holes) in stats for the REPAIR /
ARTIFACT-SESSION routes (plan §1.4).

Why: retrieval, `apply?` and `exact?` are keyed on the goal's CURRENT head relation; a proof that first strengthens the relation (⊆ to <+,
≤ to =, ..) and then closes every case with the stronger relation's congruences is invisible to all of them. The template makes that one
move mechanically and lets Lean judge.

Rule (fires only when every item holds; each miss is a recorded skip, explain() lists them):
  R      the statement's conclusion (after its ∀ / → prefix; a depth-0 ↔ ∧ ∨ → makes it a non-relation goal) is `lhs R rhs` for a
         relation R read at bracket depth 0: an infix of NOTATION (⊆ ⊂ ≤ < = ∈ ~ <+ <+: <:+ <:+: ≈ ≡), a method form `(lhs).Name rhs` /
         `lhs.Name rhs` or a prefix form `Name lhs rhs` whose last component is a relation name of the table (any namespace: `List.Subset`
         is matched by every table key ending `.Subset` and by the notation head of ⊆).
  shape  lhs and rhs are COMPONENTWISE: both applications (`f ..`, `g ..`, heads may differ) or method chains (`x.f.g ..`: an application
         whose head is the last method and whose root is the chain's first identifier), sharing at least one identifier; or both the same
         depth-0 infix constructor (++ :: + * ∪ ∩ ∘ •) with componentwise parts; one side may be a bare variable. A literal, a lambda, a
         notation form (`‖x‖`, `⟪..⟫`) or a different constructor shape than the other side does not fire (the B §3 counter-example:
         `f x ⊆ g x ++ [h]`).
  table  R (any of its heads) has a strengthening R' ⇒ R in the table whose R' has congruences or a reflexivity rule of its own, or R
         itself has congruences (then the no-strengthening plan alone). `=` is never strengthened: Eq is the finest relation on any
         carrier and the table's S-rows for Eq are specialisations on particular carriers (ModEq, EventuallyEq ..), not strengthenings.
Candidates (joint, the whole body replaced; with hypotheses in the type: `intros` (kept) or `rintro - ..` (discarded: a hypothesis over
the induction variable would enter the motive and the induction hypotheses would stop matching `assumption`) first):
  strengthen   none | apply S for each strengthening of R (dir imp / flip: `apply S`; iff_mpr: `apply S.mpr`; iff_mp: `apply S.mp`),
               at most STRENGTHEN_MAX, those whose R' has the most congruences in the table first
  induct       none | `fun_induction f ..` for each application subterm of lhs then rhs whose head is a function name (lower-case last
               component; binder groups `(x : T)` and lambdas are not applications) (≤ INDUCT_MAX) | `induction x` for the first
               INDUCT_VARS shared identifiers that the statement itself binds (binder or ∀ names: a free function name is never an
               induction target)
  probe        stage 1 (one reading per strengthen x induct x prefix plan, PROBE_MAX): the plan alone; accepted when it runs to
               `unsolved goals` (or compiles); its goal text names the constructors the closers should know and its goal count is the
               skeleton's hole count
  close        the closer table for R' (CLOSERS): `repeat' first | assumption | apply <refl R'> | apply <least R'> | apply <congruence R'
               over c> ..` with the congruences ranked (constructors named in the probe's goals by notation first, then by last component,
               then by namespace root, then by how many rules the table has for the constructor), k ∈ CLOSER_K, each without and with a
               normaliser line (`all_goals simp only` / `dsimp only`: the induction leaves the function's equations folded); the same
               lemmas as a simp set (`all_goals simp_all [..]`, k = CLOSER_K[0]); and the UNIFORM closers: the closer table's
               argument-free tactics that close the hypothesis, reflexivity, congruence and rewrite-by-hypothesis goals (closers.json
               ids hyp / refl / congr_arg / rw_hyp) in the row's scope (core for a library without Mathlib, mathlib otherwise), the
               cheapest UNIFORM_MAX by median heartbeats, cheap ones first.
  A plan carries a technique (a strengthening or an induction): a closer on the raw goal, with or without intros, is not a template.
  using        when `induction x` fails because x's type is not an inductive type (a quotient, a structure wrapper), stage 1b retries
               `induction x using N.induction` and `N.induction_on` for the USING_MAX namespace roots the failing goal names most
               (the library's own eliminators are named after its types; Lean judges which exists)
  Ordered strengthen-first (the measured insight), then induct, then closer; the first MAX_CANDIDATES are read.
Screen: harness.tools.famkit.Screen (paired workbench readings); a survivor compiles and improves the estimated score by more than BAR
points; N_OUT survivors by estimate reach the end stage, which measures them on the meter and banks through accept.decide with the
all-pin confirmation.
Near-misses (stats["near_miss"], ≤ NEAR_MISS_N, holes ≤ NEAR_MISS_HOLES): for every accepted plan the reading with the fewest open goals
whose errors are all `unsolved goals` (the plan alone = the skeleton, or plan + closer); recorded as the template text with
`all_goals sorry` appended (flat tactic block, so the appended line reaches every open goal: it compiles with exactly those holes by
construction; `sorry` is forbidden on the workbench, so it is not re-read), the hole count, the first NEAR_MISS_GOALS goal texts, the
token count and the plan note. The end stage writes stats under stats.t11 in report.jsonl; the REPAIR route (≤ 3 holes) and the
ARTIFACT-SESSION route (4-6 holes) read them from there.
Logging contract (docs/b63_logging_contract.md §1) — stats: sites, variants, readings, compiled, survivors, seconds, skips {reason: n},
errors {class: n}, peak_rss_mb, budget_out; plus probes, probes_accepted, probe_verdicts, compiled_templates (every compiling
template's reading), near_miss, near_miss_best_holes, site. banked / delta_meter are the end stage's (report families.t11.banked /
d_score, decisions with family t11): the family never banks by itself.
"""
from __future__ import annotations

import hashlib, re, time

from harness.tools import famkit as K

OPS = ("t11:template",)
_T_relations = K.load_table("relations")
TABLES = {   # provenance_audit registry (b63 r7): the generated tables this family reads through famkit.load_table
    "relations": {"rule": _T_relations.get("rule", "missing: run harness/tools/tables/gen_relations.py"), "query": _T_relations.get("query", "python3 harness/tools/tables/gen_relations.py (inside a capped systemd unit)"),
            "generated_at": _T_relations.get("generated_at"), "path": "harness/tools/tables/relations.json"},
}
CLOSER_K = (4, 8, 2)
SEARCH_SECONDS = 150.0
MAX_CHECKS = 240
N_OUT = 4
BAR = 0.05
FALLBACK = 6          # without a workbench: unscreened candidates handed to the end stage's batch screen
MIN_TIMEOUT_S = 10.0
TIMEOUT_MULT = 4.0

NOTATION = {   # Lean notation (Init / Mathlib) -> head constant of the relation
    "⊆": ["HasSubset.Subset"], "⊂": ["HasSSubset.SSubset"], "≤": ["LE.le"], "<": ["LT.lt"], "=": ["Eq"],
    "∈": ["Membership.mem"], "~": ["List.Perm"], "<+": ["List.Sublist"], "<+:": ["List.IsPrefix"],
    "<:+": ["List.IsSuffix"], "<:+:": ["List.IsInfix"], "≈": ["HasEquiv.Equiv"], "≡": ["Int.ModEq", "Nat.ModEq"],
}
NOTATION_NAMES = {"Subset": "⊆", "SSubset": "⊂", "le": "≤", "lt": "<", "Perm": "~", "Sublist": "<+", "mem": "∈", "Mem": "∈",
                  "IsPrefix": "<+:", "IsSuffix": "<:+", "IsInfix": "<:+:"}
CONNECTIVES = ("↔", "∧", "∨", "→")            # at depth 0 the conclusion is not one relation goal (checked before any relation symbol)
EXCLUDE_INFIX = {"=>", ":=", "==", "<=", ">=", "<-", "->", "<;>", "<|", "|>", "≠", "≥", ">"}
NO_STRENGTHEN = {"Eq"}                         # the finest relation: its S-rows are carrier specialisations, not strengthenings
CTOR_INFIX = ("++", "::", "+", "*", "∪", "∩", "∘", "•")
CTOR_NOTATION = {"++": "HAppend.hAppend", "::": "List.cons", "+": "HAdd.hAdd", "*": "HMul.hMul", "∪": "Union.union", "∩": "Inter.inter",
                 "\\": "SDiff.sdiff", "•": "HSMul.hSMul", "∘": "Function.comp", "-": "HSub.hSub", "⁻¹": "Inv.inv", "insert": "Insert.insert",
                 "[]": "List.nil", "∅": "EmptyCollection.emptyCollection", "⊆": "HasSubset.Subset", "×ˢ": "SProd.sprod"}
STRENGTHEN_MAX = 6
INDUCT_MAX = 4
INDUCT_VARS = 2
PROBE_MAX = 48        # stage-1 probes (strengthening x induction x hypothesis prefix) per row
UNIFORM_GOALS = ("hyp", "refl", "congr_arg", "rw_hyp")   # closers.json goal ids a uniform closer must close
UNIFORM_MAX = 4
UNIFORM_FALLBACK = ("simp_all", "grind")                  # without the closer table
NO_MATHLIB = ("strata",)                                  # libraries whose environment has no Mathlib: the core scope
NORMALISERS = ((None, ""), ("all_goals simp only", "+simp_only"), ("all_goals dsimp only", "+dsimp_only"))
MAX_CANDIDATES = 160
USING_MAX = 2                                             # namespace roots tried as `induction x using N.induction[_on]`
USING_PRINCIPLES = ("induction", "induction_on")
NOT_INDUCTIVE = "not an inductive type"
NEAR_MISS_N = 3
NEAR_MISS_HOLES = 6
NEAR_MISS_GOALS = 3
IDENT_RE = r"[A-Za-z_α-ωΑ-Ω𝓐-𝔃][\w'!?₀-₉]*"
NAME_RE = r"[A-Za-z_α-ωΑ-Ω][\w'!?₀-₉.]*"


def proof_key(proof: str) -> str:
    return hashlib.sha256(proof.strip().encode()).hexdigest()[:16]


def _tbl() -> dict:
    return K.load_table("relations")


def _in_env(rec: dict, source: str | None) -> bool:
    """A table record holds for the row when the query saw it in the row's library environment (strata has no Mathlib)."""
    if not source:
        return True
    envs = rec.get("envs") or []
    return any(f"/{source}-" in e or e.endswith(source) for e in envs)


def _rows(T: dict, sec: str, R: str, source: str | None) -> list[dict]:
    return [r for r in (T.get(sec) or {}).get(R) or [] if _in_env(r, source)]


# ------------------------------------------------------------------------------------------------------------------- statement
def _strip(s: str) -> str:
    s = s.strip()
    while s.startswith("(") and s.endswith(")"):
        g = K._groups(s)
        if g and g[0] == (0, len(s)):
            s = s[1:-1].strip()
        else:
            break
    return s


def relation_of(concl: str) -> dict | None:
    """{"heads": [R..], "sym", "lhs", "rhs"} for the conclusion's top-level relation, or None (with "why" in the skip dict of sites())."""
    c = _strip(concl)
    cut = K.depth0_positions(c, [":="])
    if cut:
        c = c[:cut[0][0]].strip()
    if re.match(r"^(∀|∃|¬|Π|Σ)", c):
        return None
    if K.depth0_positions(c, list(CONNECTIVES)):   # a connective binds looser than any relation: not one relation goal
        return None
    seps = list(NOTATION) + sorted(EXCLUDE_INFIX)
    for p, s in K.depth0_positions(c, seps):
        if s in EXCLUDE_INFIX:
            return None     # `≠`, `≥`, `>`: not in the table's orientation; a `:=`-like token: not a Prop
        lhs, rhs = c[:p].strip(), c[p + len(s):].strip()
        if not lhs or not rhs:
            continue
        return {"heads": list(NOTATION[s]), "sym": s, "lhs": lhs, "rhs": rhs}
    # method form `(x).Name y` / `x.Name y` and prefix form `Name x y`
    m = re.match(r"^(\(.*?\)|[^\s()]+)\.([A-Za-z_][\w'!?₀-₉]*)\s+(.+)$", c, re.S)
    if m and K._groups(m.group(1)) in ([], [(0, len(m.group(1)))]) and len(_args(m.group(3))) == 1:   # one argument: `x.R y`
        name = m.group(2)
        heads = _heads_named(name)
        if heads:
            return {"heads": heads, "sym": "." + name, "lhs": _strip(m.group(1)), "rhs": m.group(3).strip()}
    m = re.match(r"^(" + NAME_RE + r")\s+(.+)$", c, re.S)
    if m:
        args = _args(m.group(2))
        name = m.group(1).split(".")[-1]
        heads = _heads_named(name, full=m.group(1))
        if heads and len(args) == 2:
            return {"heads": heads, "sym": m.group(1), "lhs": _strip(args[0]), "rhs": _strip(args[1])}
    return None


def _heads_named(name: str, full: str | None = None) -> list[str]:
    T = _tbl()
    keys = set()
    for sec in ("strengthen", "congruence", "refl", "least", "one_sided"):
        keys.update((T.get(sec) or {}).keys())
    out = [k for k in keys if k.split(".")[-1] == name or k == full]
    if name in NOTATION_NAMES:
        out += NOTATION[NOTATION_NAMES[name]]
    return sorted(set(out), key=lambda k: (k not in NOTATION.get(NOTATION_NAMES.get(name, ""), []), k))


def _args(s: str) -> list[str]:
    """Depth-0 whitespace-separated arguments."""
    out, depth, cur = [], 0, ""
    for ch in s:
        if ch in K.OPEN:
            depth += 1
        elif ch in K.CLOSE:
            depth -= 1
        if ch.isspace() and depth == 0:
            if cur:
                out.append(cur)
            cur = ""
        else:
            cur += ch
    if cur:
        out.append(cur)
    return out


def _is_name(tok: str) -> bool:
    return bool(re.fullmatch(NAME_RE, tok))


def _chain(head: str) -> dict | None:
    """`x.f.g` / `(e).f.g` as a method chain: {"root": first identifier or None, "method": last component} or None (a plain name)."""
    if head.startswith("("):
        g = K._groups(head)
        if not g or g[0][0] != 0:
            return None
        tail = head[g[0][1]:]
        if not tail.startswith(".") or not re.fullmatch(r"(\.[A-Za-z_][\w'!?₀-₉]*)+", tail):
            return None
        inner = _strip(head[:g[0][1]])
        ids = _idents(inner)
        root = ids[0].split(".")[0] if ids else None
        return {"root": root if root and root[:1].islower() else None, "method": tail.split(".")[-1], "receiver": inner}
    if not _is_name(head) or "." not in head:
        return None
    parts = head.split(".")
    if parts[0][:1].islower() and len(parts) >= 2 and not any(p[:1].isupper() for p in parts[1:]):
        return {"root": parts[0], "method": parts[-1], "receiver": ".".join(parts[:-1])}   # `xs.reverse.length`: a chain on xs
    return None


def shape(side: str) -> dict:
    s = _strip(side)
    for p, op in K.depth0_positions(s, list(CTOR_INFIX)):
        l, r = s[:p].strip(), s[p + len(op):].strip()
        if l and r:
            return {"kind": "ctor", "ctor": op, "parts": [shape(l), shape(r)]}
    if s.startswith(("[", "{", "⟨")):
        return {"kind": "literal"}
    if re.match(r"^(fun|λ)\b", s):
        return {"kind": "lambda"}
    args = _args(s)
    if not args:
        return {"kind": "empty"}
    head = args[0]
    ch = _chain(head)
    if ch is not None:
        return {"kind": "app", "head": ch["method"], "args": [ch["receiver"]] + args[1:], "root": ch["root"], "chain": True}
    if len(args) == 1:
        if _is_name(head):
            return {"kind": "var", "head": head}
        return {"kind": "other"}
    head_id = head.split(".")[-1] if _is_name(head) else None
    return {"kind": "app", "head": head if head_id else None, "args": args[1:]}


def componentwise(a: dict, b: dict) -> bool:
    if a["kind"] == "app" and b["kind"] == "app":
        return True
    if a["kind"] == "ctor" and b["kind"] == "ctor" and a["ctor"] == b["ctor"]:
        return all(componentwise(x, y) for x, y in zip(a["parts"], b["parts"]))
    if a["kind"] == "app" and b["kind"] == "var" or a["kind"] == "var" and b["kind"] == "app":
        return True   # `f x R x`-type goals: one side is the induction variable itself
    return False


def _idents(s: str) -> list[str]:
    """Identifiers as written, plus the receiver of a method chain (`xs.map` names xs too: a lower-case root is a variable, not a namespace)."""
    out = []
    for m in K.IDENT.finditer(s):
        out.append(m.group(0))
        root = m.group(0).split(".")[0]
        if "." in m.group(0) and root[:1].islower() and root not in out:
            out.append(root)
    return out


def _heads_in(sh: dict) -> list[str]:
    if sh["kind"] == "app" and sh.get("head"):
        return [sh["head"]]
    if sh["kind"] == "ctor":
        return [h for p in sh["parts"] for h in _heads_in(p)]
    return []


def bound_names(P: dict) -> tuple[list[str], int]:
    """(names the statement binds: binder names, ∀-prefix names; the number of ∀ names + → arrows before the conclusion)."""
    names = [b["name"] for b in P.get("binders") or [] if b.get("name") and b["kind"] != "inst"]
    names = [n for nm in names for n in nm.split()]
    t = P.get("type") or ""
    hyps = 0
    while True:
        t2 = t.lstrip()
        if t2.startswith(("∀", "Π")):
            cm = next((p for p, _ in K.depth0_positions(t2, [","])), None)
            if cm is None:
                break
            seg = t2[1:cm]
            k = 0
            for a, b in K._groups(seg):
                g = seg[a + 1:b - 1]
                cp = [p for p, _ in K.depth0_positions(g, [":"])]
                for n in (g[:cp[0]] if cp else g).split():
                    if re.fullmatch(IDENT_RE, n):
                        names.append(n)
                        k += 1
            rest = re.sub(r"[(\[{⦃].*?[)\]}⦄]", " ", seg)
            for n in rest.split():
                if re.fullmatch(IDENT_RE, n):
                    names.append(n)
                    k += 1
            hyps += max(1, k)
            t = t2[cm + 1:]
            continue
        arrows = K.depth0_positions(t2, ["→"])
        if arrows:
            hyps += 1
            t = t2[arrows[0][0] + 1:]
            continue
        break
    return names, hyps


# ------------------------------------------------------------------------------------------------------------------- generation
def _ctor_weight(T: dict, R: str, source: str | None) -> dict:
    w: dict = {}
    for sec in ("congruence", "one_sided"):
        for r in _rows(T, sec, R, source):
            w[r["ctor"]] = w.get(r["ctor"], 0) + 1
    return w


def goal_features(goal_text: str) -> dict:
    """What the goals name: notation constructors (CTOR_NOTATION), identifier last components and namespace roots."""
    ids = _idents(goal_text)
    return {"ctors": {c for sym, c in CTOR_NOTATION.items() if sym in goal_text},
            "short": {i.split(".")[-1] for i in ids}, "roots": {i.split(".")[0] for i in ids if "." in i}}


def _closer_lemmas(T: dict, R: str, feat: dict, k: int, source: str | None) -> list[str]:
    """`apply` targets for the table closer on relation R: one refl, least elements, then k congruences (same relation at every related
    position) ranked by constructor: named in the goals by notation first, then by its last component, then by its namespace root, then by
    the table's weight of the constructor (how many rules mention it: the generic ones first)."""
    w = _ctor_weight(T, R, source)

    def rank(r):
        c = r["ctor"]
        return (-(c in feat["ctors"]), -(c.split(".")[-1] in feat["short"]), -(c.split(".")[0] in feat["roots"]), -w.get(c, 0), r.get("arity", 0), r["thm"])
    out: list[str] = []
    for r in _rows(T, "refl", R, source):
        out.append(r["thm"])
        break
    least = sorted(_rows(T, "least", R, source), key=rank)
    out += [r["thm"] for r in least if r["ctor"].split(".")[0] in feat["roots"] or r["ctor"] in feat["ctors"]][:2]
    seen = set()
    for r in sorted([r for r in _rows(T, "congruence", R, source) if r.get("same")], key=rank):
        if r["ctor"] in seen:
            continue
        seen.add(r["ctor"])
        out.append(r["thm"])
        if len(seen) >= k:
            break
    return out


def _strengthenings(T: dict, heads: list[str], source: str | None, skips: list | None = None) -> list[dict]:
    out = []
    for R in heads:
        if R in NO_STRENGTHEN:
            if skips is not None:
                skips.append({"what": f"strengthenings of {R}", "why": "the finest relation is never strengthened (NO_STRENGTHEN)"})
            continue
        for s in _rows(T, "strengthen", R, source):
            Rp = s["from"]
            n_c = len([r for r in _rows(T, "congruence", Rp, source) if r.get("same")])
            if n_c == 0 and not _rows(T, "refl", Rp, source):
                if skips is not None:
                    skips.append({"what": f"strengthening {s['thm']} ({Rp} ⇒ {R})", "why": "R' has no congruence and no refl in the table"})
                continue   # a stronger relation with no closers of its own buys nothing
            out.append(dict(s, R=R, n_cong=n_c))
    best: dict = {}   # one per (from, dir): the shortest name
    for s in out:
        key = (s["from"], s["dir"])
        if key not in best or len(s["thm"]) < len(best[key]["thm"]):
            best[key] = s
    ranked = sorted(best.values(), key=lambda s: (-s["n_cong"], len(s["thm"]), s["thm"]))
    if skips is not None:
        for s in ranked[STRENGTHEN_MAX:]:
            skips.append({"what": f"strengthening {s['thm']} ({s['from']} ⇒ {s['R']})", "why": f"beyond STRENGTHEN_MAX={STRENGTHEN_MAX}"})
    return ranked[:STRENGTHEN_MAX]


def _applications(concl: str, skips: list | None = None) -> list[str]:
    """Application subterms `f a ..` of the conclusion whose head's last component starts lower-case (a function, not a constructor) or
    whose head is a method chain: the sides and every parenthesised group inside them, outermost first, text as written. Binder groups
    `(x : T)`, lambdas and `∫ ..`-like binder notation are not applications."""
    out = []

    def walk(t: str, depth: int):
        t = _strip(t)
        if K.depth0_positions(t, [":"]) and not K.depth0_positions(t, [":="]):
            if skips is not None:
                skips.append({"what": t[:60], "why": "binder group (`x : T`), not an application"})
            return
        if re.match(r"^(fun|λ|∫|∑|∏|⨆|⨅|∀|∃)\b", t) or t[:1] in "∫∑∏⨆⨅":
            if skips is not None:
                skips.append({"what": t[:60], "why": "binder notation, not an application"})
            return
        args = _args(t)
        if len(args) >= 2 and (_chain(args[0]) is not None or (_is_name(args[0]) and args[0].split(".")[-1][:1].islower())):
            if t not in out:
                out.append(t)
        elif len(args) >= 2 and skips is not None and depth == 0:
            skips.append({"what": t[:60], "why": "head is not a function name (constructor / notation)"})
        if depth >= 3:
            return
        for a, b in K._groups(t):
            if t[a] == "(":
                walk(t[a + 1:b - 1], depth + 1)
    walk(concl, 0)
    return out


def function_positions(concl: str) -> set[str]:
    """Identifiers that occur as the head of an application somewhere in the conclusion (`f a`, `(f a).m b`: f and the chain head)."""
    out: set = set()

    def walk(t: str, depth: int):
        t = _strip(t)
        args = _args(t)
        if len(args) >= 2 and _is_name(args[0]):
            out.add(args[0])
            if args[0].split(".")[0][:1].isupper():   # `Foo.bar a`: the namespace root too (a chain root `xs.map f` is a receiver)
                out.add(args[0].split(".")[0])
        if depth >= 4:
            return
        for a, b in K._groups(t):
            walk(t[a + 1:b - 1], depth + 1)
    walk(concl, 0)
    return out


def sites(proof: str, statement: str, source: str | None = None) -> dict:
    """The template's reading of the statement: {"fire": bool, "why": skip reason, "rel", "shape", "strengthen": [...], "inducts": [...],
    "skips": [{"what", "why"}] (constructs considered and dropped)}."""
    P = K.statement_parts(statement)
    if not P.get("ok"):
        return {"fire": False, "why": "statement not parsed", "skips": []}
    skips: list = []
    rel = relation_of(P["concl"])
    if rel is None:
        return {"fire": False, "why": "conclusion is not a relation goal", "skips": skips}
    sl, sr = shape(rel["lhs"]), shape(rel["rhs"])
    if not componentwise(sl, sr):
        return {"fire": False, "why": f"sides not componentwise ({sl['kind']}/{sl.get('ctor', '')} vs {sr['kind']}/{sr.get('ctor', '')})",
                "rel": rel["sym"], "skips": skips}
    if sl["kind"] == "var" and sr["kind"] == "var":
        return {"fire": False, "why": "both sides are variables", "rel": rel["sym"], "skips": skips}
    shared = set(_idents(rel["lhs"])) & set(_idents(rel["rhs"]))
    if not shared:
        return {"fire": False, "why": "sides share no identifier", "rel": rel["sym"], "skips": skips}
    T = _tbl()
    if not T:
        return {"fire": False, "why": "relation table missing", "skips": skips}
    S = _strengthenings(T, rel["heads"], source, skips)
    own = [R for R in rel["heads"] if any(r.get("same") for r in _rows(T, "congruence", R, source))]
    if not S and not own:
        return {"fire": False, "why": "no strengthening and no congruence in the table for " + "/".join(rel["heads"]), "rel": rel["sym"], "skips": skips}
    apps = _applications(rel["lhs"], skips) + _applications(rel["rhs"], skips)
    inducts = [f"fun_induction {a}" for a in apps[:INDUCT_MAX]]
    for a in apps[INDUCT_MAX:]:
        skips.append({"what": a[:60], "why": f"beyond INDUCT_MAX={INDUCT_MAX}"})
    _bound, hyps = bound_names(P)
    fpos = function_positions(rel["lhs"]) | function_positions(rel["rhs"])
    cand_vars = []
    for sh in (sl, sr):
        for a in ([sh.get("root")] if sh.get("root") else []) + (sh.get("args") or []) + ([sh["head"]] if sh["kind"] == "var" else []):
            if a and re.fullmatch(IDENT_RE, a) and a in shared and a not in cand_vars:
                cand_vars.append(a)
    ind_vars = [a for a in cand_vars if a not in fpos and "." not in a]
    for a in cand_vars:
        if a not in ind_vars:
            skips.append({"what": a, "why": "shared identifier in function position (a function, not a variable): no `induction`"})
    inducts += [f"induction {a}" for a in ind_vars[:INDUCT_VARS]]
    return {"fire": True, "rel": rel["sym"], "heads": rel["heads"], "shape": (sl["kind"], sr["kind"]), "strengthen": S, "own": own,
            "inducts": inducts, "hyps": hyps, "source": source, "skips": skips,
            "chain": bool(sl.get("chain") or sr.get("chain"))}


def _head(proof: str, statement: str) -> str | None:
    body = K.body_of(proof, statement)
    if body is None:
        return None
    return proof[:len(proof) - len(body)].rstrip()


def pres_of(info: dict) -> list[tuple]:
    """The hypothesis prefix variants: none (no hypotheses); `intros` (keep them: the closers may need them) and `rintro - ..` (discard
    them: a kept hypothesis over the induction variable enters the motive and the induction hypotheses stop matching `assumption`)."""
    n = int(info.get("hyps") or 0)
    if n <= 0:
        return [()]
    return [("intros",), ("rintro " + " ".join("-" for _ in range(n)),)]


def plans_of(info: dict) -> list[tuple]:
    """(strengthening tactic or None, relation the closers are for, strengthening name or None, induction tactic or None, prefix lines)."""
    first = []
    for s in info["strengthen"]:
        tac = {"imp": f"apply {s['thm']}", "flip": f"apply {s['thm']}", "iff_mpr": f"apply {s['thm']}.mpr", "iff_mp": f"apply {s['thm']}.mp"}[s["dir"]]
        first.append((tac, s["from"], s["thm"]))
    for R in info["own"]:
        first.append((None, R, None))
    out = [(tac, R, sn, ind, pre) for tac, R, sn in first for ind in [None] + list(info["inducts"]) for pre in pres_of(info)]
    return [p for p in out if p[0] or p[3]][:PROBE_MAX]   # a plan carries a technique: a strengthening or an induction


def _decl(head: str, lines: list[str]) -> str:
    body = ":= by\n" + "\n".join("  " + l for l in lines)
    return head + body[2:] if head.endswith(":=") else head + " " + body


def probe_decl(head: str, info: dict, plan: tuple) -> str:
    tac, _R, _sn, ind, pre = plan
    return _decl(head, list(pre) + ([tac] if tac else []) + ([ind] if ind else []))


def plan_note(plan: tuple) -> str:
    tac, R, sn, ind, pre = plan
    return f"{sn or R}; {ind or 'no induction'}; {pre[0] if pre else 'no intro'}"


def uniform_closers(source: str | None) -> list[tuple[str, bool]]:
    """[(tactic, expensive)] from the closer table: argument-free tactics that close every UNIFORM_GOALS synthetic goal in the row's scope,
    the cheapest UNIFORM_MAX by median heartbeats (cheap-cost ones before expensive ones)."""
    C = K.load_table("closers")
    scopes = (C or {}).get("scopes") or {}
    scope = "core" if (source or "") in NO_MATHLIB or "mathlib" not in scopes else "mathlib"
    rows = (scopes.get(scope) or {}).get("closers") or []
    picked = []
    for c in rows:
        if set(UNIFORM_GOALS) <= set(c.get("closes") or []) and c.get("tactic"):
            picked.append((c["tactic"], c.get("cost") == "expensive", float(c.get("hb_median") or 1e9)))
    picked.sort(key=lambda x: (x[1], x[2], x[0]))
    out = [(t, e) for t, e, _ in picked[:UNIFORM_MAX]]
    return out or [(t, True) for t in UNIFORM_FALLBACK]


def closers_for(T: dict, R: str, feat: dict, source: str | None) -> list[tuple]:
    """[(closer lines, tag, expensive)]: the table closer at k congruences, each without and with a normaliser line before it (`all_goals
    simp only`: the induction leaves the function's equations folded in the goal, the congruences need the constructors visible), the
    same lemmas as a simp set, then the uniform closers."""
    out, seen = [], set()
    first_lem = None
    for k in CLOSER_K:
        lem = _closer_lemmas(T, R, feat, k, source)
        if not lem:
            continue
        first_lem = first_lem or lem
        cl = "repeat' first | " + " | ".join(["assumption"] + [f"apply {l}" for l in lem])   # repeat' works on every open goal
        if cl in seen:
            continue
        seen.add(cl)
        for norm, ntag in NORMALISERS:
            out.append(((([norm] if norm else []) + [cl]), f"k{k}{ntag}", False))
    if first_lem:
        out.append(([f"all_goals simp_all [{', '.join(first_lem)}]"], f"simp_all+k{CLOSER_K[0]}", False))
    for u, exp in uniform_closers(source):
        out.append(([f"all_goals {u}"], u, exp))
    return out


def generate(proof: str, statement: str, *, info: dict | None = None, plans: list | None = None, feats: dict | None = None,
             source: str | None = None) -> list[dict]:
    """[{"op", "decl", "note", "expensive", "plan"}] the template candidates: for every plan (strengthening x induction; `plans`: the ones
    a stage-1 probe accepted, else all) the closers built from the goals' features (`feats` per plan: from the probe's unsolved goals, else
    from the statement). Pure."""
    info = info or sites(proof, statement, source)
    if not info.get("fire"):
        return []
    head = _head(proof, statement)
    if head is None:
        return []
    T = _tbl()
    src = info.get("source") or source
    out, seen = [], set()
    for plan in (plans if plans is not None else plans_of(info)):
        tac, R, sname, ind, pre = plan
        feat = (feats or {}).get(plan) or goal_features(statement)
        for cl, ctag, exp in closers_for(T, R, feat, src):
            decl = _decl(head, list(pre) + ([tac] if tac else []) + ([ind] if ind else []) + cl)
            if decl.strip() == proof.strip() or decl in seen:
                continue
            seen.add(decl)
            note = f"{plan_note(plan)}; {ctag}"
            out.append({"op": "t11:template", "decl": decl, "note": note[:300], "expensive": exp, "plan": plan})
    return out[:MAX_CANDIDATES]


PROBE_OK = ("unsolved goals",)
PROBE_BAD = ("could not find suitable call", "unknown identifier", "unknown constant", "failed to unify", "could not unify",
             "apply failed", "not a structural", "fun_induction", "unexpected token", "failed to synthesize", "type mismatch",
             "unknown free variable", "motive is not type correct", "failed to generalize", "index in target's type is not a variable")


def _errs(r: dict) -> list[str]:
    return [str(e) for e in (r.get("errors") or [])] or ([str(r.get("error"))] if r.get("error") else [])


def probe_verdict(r: dict) -> tuple[bool, str]:
    """(accepted, goal text): a stage-1 probe is accepted when it ran to the end and only left goals open (every error is `unsolved goals`),
    or when it compiled outright."""
    if r.get("status") == "ok":
        return True, ""
    errs = _errs(r)
    if not errs or any(any(b in e.lower() for b in PROBE_BAD) for e in errs):
        return False, ""
    if all(any(o in e.lower() for o in PROBE_OK) for e in errs):
        return True, "\n".join(errs)
    return False, ""


def open_goals(err_text: str) -> list[str]:
    """The goals of `unsolved goals` messages: each `⊢` line with the `case ..` tag before it, in order."""
    out, tag, cur = [], None, None
    for line in err_text.splitlines():
        s = line.strip()
        if not s or s.startswith("case ") or re.match(r"^\d+:\d+:", s):
            if cur is not None:
                out.append(cur)
                cur = None
            tag = s if s.startswith("case ") else None
        elif "⊢" in s:
            if cur is not None:
                out.append(cur)
            cur = (tag + " " if tag else "") + s[s.index("⊢"):]
            tag = None
        elif cur is not None:   # a goal continued on the next line (indented)
            cur += " " + s
    if cur is not None:
        out.append(cur)
    return out


def near_miss_of(decl: str, r: dict, note: str) -> dict | None:
    """A reading whose errors are all `unsolved goals` as a near-miss record, or None (too many holes, or other errors)."""
    ok, goals = probe_verdict(r)
    if r.get("status") == "ok" or not ok or not goals:
        return None
    gl = open_goals(goals)
    n = len(gl)
    if n == 0 or n > NEAR_MISS_HOLES:
        return None
    holed = decl.rstrip() + "\n  all_goals sorry"
    try:
        from scorer.tokenize import count_tokens
        tok = count_tokens(holed)
    except Exception:  # noqa: BLE001
        tok = None
    return {"holes": n, "goals": [g[:400] for g in gl[:NEAR_MISS_GOALS]], "decl_holed": holed, "tokens": tok, "note": note[:200],
            "first_error": _errs(r)[0][:200] if _errs(r) else "", "verified": "by construction (flat tactic block; every error is `unsolved goals`)"}


# ------------------------------------------------------------------------------------------------------------------- contract
def _timeout(ctx: dict | None) -> float:
    cs = (ctx or {}).get("compile_s")
    return max(MIN_TIMEOUT_S, TIMEOUT_MULT * float(cs) + 4.0) if isinstance(cs, (int, float)) else MIN_TIMEOUT_S * 3


def _bump(st: dict, key: str, why: str) -> None:
    st[key][why] = st[key].get(why, 0) + 1


def _finish(st: dict, t0: float, wb=None) -> None:
    st["seconds"] = round(st.get("seconds", 0.0) + time.time() - t0, 2)
    if wb is not None:
        st["peak_rss_mb"] = getattr(wb, "peak_rss_mb", None)


def search(proof: str, statement: str, wb, *, meter_reading: dict | None = None, exchange=None, ctx: dict | None = None,
           stats: dict | None = None, log=None, deadline: float | None = None, max_checks: int = MAX_CHECKS, n_out: int = N_OUT,
           stage_caps: dict | None = None, trace: list | None = None) -> dict:
    """The t5 contract: {"t11_found": [{"op", "decl", "note", "est"}], "t11_found_for": proof_key(proof)} (survivors by estimate); stats as
    in the module docstring (near-misses included)."""
    t0 = time.time()
    st = stats if stats is not None else {}
    log = log or (lambda *a: None)
    for k_, v_ in (("sites", 0), ("variants", 0), ("readings", 0), ("compiled", 0), ("survivors", 0), ("skips", {}), ("errors", {}),
                   ("budget_out", False), ("searches", 0), ("near_miss", []), ("near_miss_best_holes", None), ("peak_rss_mb", None)):
        st.setdefault(k_, v_ if not isinstance(v_, (dict, list)) else type(v_)(v_))
    st["searches"] += 1
    source = (ctx or {}).get("source") or (getattr(wb, "row", None) or {}).get("source")
    info = sites(proof, statement, source)
    st["static_skips"] = [f"{s['what']}: {s['why']}"[:160] for s in (info.get("skips") or [])][:24]
    if not info.get("fire"):
        _bump(st, "skips", info.get("why", "?"))
        _finish(st, t0, wb)
        return {}
    st["sites"] = max(st["sites"], 1)
    st["site"] = {"rel": info["rel"], "shape": list(info["shape"]), "strengthen": [s["thm"] for s in info["strengthen"]],
                  "inducts": info["inducts"], "chain": info.get("chain", False), "hyps": info.get("hyps")}
    head = _head(proof, statement)
    if head is None:
        _bump(st, "skips", "proof body not split")
        _finish(st, t0, wb)
        return {"t11_found": [], "t11_found_for": proof_key(proof)}   # searched, nothing: no unscreened fallback
    plans = plans_of(info)
    dl = deadline if deadline is not None else time.time() + SEARCH_SECONDS
    caps = dict(stage_caps or {})
    # stage 1: does the strengthening apply and the induction run? (the probe's unsolved goals name the constructors for the closers)
    plans = plans[:int(caps.get("probes", PROBE_MAX))]
    accepted, feats, ok_probe, near = [], {}, [], []
    probes = [probe_decl(head, info, p) for p in plans]
    t1 = time.time()
    try:
        prs = wb.check(probes, timeout=_timeout(ctx))
    except Exception as e:  # noqa: BLE001
        st["errors"][type(e).__name__] = st["errors"].get(type(e).__name__, 0) + 1
        prs = []
    st["probe_seconds"] = round(st.get("probe_seconds", 0.0) + time.time() - t1, 2)
    st["probes"] = st.get("probes", 0) + len(prs)
    verdicts = {}
    for p, r in zip(plans, prs):
        ok, goals = probe_verdict(r)
        verdicts[plan_note(p)] = "ok" if ok else K._err_class(r)
        if trace is not None:
            trace.append({"op": "t11:probe", "src": plan_note(p), "status": r.get("status"), "error": str(r.get("error") or "")[:200], "accepted": ok})
        if not ok:
            continue
        if r.get("status") == "ok":
            ok_probe.append((p, r))
        else:
            nm = near_miss_of(probes[plans.index(p)], r, plan_note(p) + "; skeleton")
            if nm:
                near.append(nm)
        accepted.append(p)
        feats[p] = goal_features(goals) if goals else goal_features(statement)
    # stage 1b: `induction x` on a non-inductive type -> `induction x using N.induction[_on]` for the roots the goal names most
    retries = []
    for p, r in zip(plans, prs):
        if not (p[3] or "").startswith("induction ") or " using " in p[3]:
            continue
        errs = _errs(r)
        if not any(NOT_INDUCTIVE in e for e in errs):
            continue
        roots: dict = {}
        for e in errs:
            for i in _idents(e.split("⊢", 1)[1] if "⊢" in e else e):
                if "." in i and i.split(".")[0][:1].isupper():
                    roots[i.split(".")[0]] = roots.get(i.split(".")[0], 0) + 1
        for N in sorted(roots, key=lambda k: (-roots[k], k))[:USING_MAX]:
            for pr in USING_PRINCIPLES:
                q = (p[0], p[1], p[2], f"{p[3]} using {N}.{pr}", p[4])
                if q not in retries and q not in plans:
                    retries.append(q)
    if retries and time.time() < dl:
        rdecls = [probe_decl(head, info, q) for q in retries]
        try:
            rrs = wb.check(rdecls, timeout=_timeout(ctx))
        except Exception as e:  # noqa: BLE001
            st["errors"][type(e).__name__] = st["errors"].get(type(e).__name__, 0) + 1
            rrs = []
        st["using_retries"] = st.get("using_retries", 0) + len(rrs)
        for q, r in zip(retries, rrs):
            ok, goals = probe_verdict(r)
            verdicts[plan_note(q)] = "ok" if ok else K._err_class(r)
            if trace is not None:
                trace.append({"op": "t11:probe", "src": plan_note(q), "status": r.get("status"), "error": str(r.get("error") or "")[:200], "accepted": ok})
            if not ok:
                continue
            st["using_accepted"] = st.get("using_accepted", 0) + 1
            if r.get("status") == "ok":
                ok_probe.append((q, r))
            else:
                nm = near_miss_of(rdecls[retries.index(q)], r, plan_note(q) + "; skeleton")
                if nm:
                    near.append(nm)
            accepted.append(q)
            feats[q] = goal_features(goals) if goals else goal_features(statement)
        plans = plans + retries
        prs = prs + rrs
    st["probes_accepted"] = st.get("probes_accepted", 0) + len(accepted)
    st["probe_verdicts"] = verdicts
    st["readings"] += len(prs)
    if not accepted:
        _bump(st, "skips", "no strengthening/induction probe accepted")
        _finish(st, t0, wb)
        return {"t11_found": [], "t11_found_for": proof_key(proof)}   # searched, nothing: no unscreened fallback
    cands = generate(proof, statement, info=info, plans=accepted, feats=feats, source=source)
    for p, r in ok_probe:   # a probe that compiled by itself is a candidate too
        cands.insert(0, {"op": "t11:template", "decl": probe_decl(head, info, p), "note": f"{plan_note(p)}; probe closes", "expensive": False, "plan": p})
    cands = cands[:int(caps.get("candidates", MAX_CANDIDATES))]
    st["variants"] += len(cands)
    if not cands:
        _bump(st, "skips", "no candidate")
        _finish(st, t0, wb)
        return {"t11_found": [], "t11_found_for": proof_key(proof)}   # searched, nothing: no unscreened fallback
    scr = K.Screen(wb, proof, meter_reading=meter_reading, deadline=dl, max_checks=max_checks, timeout=_timeout(ctx), log=log)
    rs = scr.read([c["decl"] for c in cands])
    by = {c["decl"]: c for c in cands}
    found = []
    for r in rs:
        c = by[r["decl"]]
        if trace is not None:
            trace.append({"op": "t11:template", "src": c["note"], "status": r.get("status"), "error": str(r.get("error") or "")[:160],
                          "d_score": r.get("d_score"), "tokens": r.get("tokens")})
        if r.get("status") == "ok":
            st.setdefault("compiled_templates", [])
            if len(st["compiled_templates"]) < 24:   # monitoring: every compiling template's reading
                st["compiled_templates"].append({"note": c["note"][:80], "d_score": r.get("d_score"), "tokens": r.get("tokens"),
                                                 "hb_est": r.get("heartbeats_est")})
            if (r.get("d_score") or 0) > BAR:
                found.append({"op": c["op"], "decl": c["decl"], "note": c["note"] + f"; est {r['d_score']:+.3f}", "est": r["d_score"],
                              "expensive": c["expensive"], "tokens": r.get("tokens"), "heartbeats_est": r.get("heartbeats_est")})
        else:
            nm = near_miss_of(r["decl"], r, c["note"])
            if nm:
                near.append(nm)
    found.sort(key=lambda c: -c["est"])
    # near-misses for the REPAIR / ARTIFACT-SESSION routes: fewest holes, then fewest tokens; one per hole count and plan note
    near.sort(key=lambda m: (m["holes"], m["tokens"] if m["tokens"] is not None else 1e9))
    kept, seen_nm = list(st["near_miss"]), set()
    for m in near:
        key = (m["holes"], m["note"].split(";")[0])
        if key in seen_nm:
            continue
        seen_nm.add(key)
        kept.append(m)
    kept.sort(key=lambda m: (m["holes"], m["tokens"] if m["tokens"] is not None else 1e9))
    st["near_miss"] = kept[:NEAR_MISS_N]
    st["near_miss_total"] = st.get("near_miss_total", 0) + len(near)
    st["near_miss_best_holes"] = min((m["holes"] for m in st["near_miss"]), default=None)
    for k_ in ("compiled", "timeouts", "calls"):
        st[k_] = st.get(k_, 0) + scr.stats[k_]
    st["budget_out"] = st["budget_out"] or scr.stats["budget_out"]
    st["readings"] += scr.stats["readings"]
    for k_, v_ in scr.stats["errors"].items():
        st["errors"][k_] = st["errors"].get(k_, 0) + v_
    st["survivors"] += len(found)
    st["wb_seconds"] = round(st.get("wb_seconds", 0.0) + scr.stats["seconds"], 2)
    _finish(st, t0, wb)
    log(f"t11: {len(found)} survivor(s) of {len(cands)} template(s), {scr.stats['compiled']} compiled, {scr.stats['readings']} readings, "
        f"{len(near)} near-miss(es) (best {st['near_miss_best_holes']} hole(s)) ({st['seconds']} s)")
    return {"t11_found": found[:n_out], "t11_found_for": proof_key(proof)}   # empty list: searched, nothing survived


def candidates(proof: str, statement: str, *, exchange: float | None = None, max_per_op: int = N_OUT, ctx: dict | None = None) -> list[dict]:
    """[{"op", "decl", "note"}]: the search's survivors (ctx["t11_found"] for this proof), else the first FALLBACK templates unscreened."""
    ctx = ctx or {}
    if ctx.get("t11_found_for") == proof_key(proof) and isinstance(ctx.get("t11_found"), list):
        out = []
        for c in ctx["t11_found"][:max_per_op]:
            if isinstance(c, dict) and isinstance(c.get("decl"), str) and c["decl"].strip() != proof.strip():
                item = {"op": c.get("op") or "t11:template", "decl": c["decl"], "note": str(c.get("note") or "")[:300]}
                if c.get("expensive"):
                    item["timeout_s"] = _timeout(ctx)
                out.append(item)
        return out
    if ctx.get("t11_found_for") is not None:   # a search ran for this proof and found nothing
        return []
    out = []
    for c in generate(proof, statement, source=ctx.get("source"))[:FALLBACK]:
        item = {"op": c["op"], "decl": c["decl"], "note": c["note"]}
        if c["expensive"]:
            item["timeout_s"] = _timeout(ctx)
        out.append(item)
    return out


def explain(proof: str, statement: str, ctx: dict | None = None) -> dict:
    """Coverage diagnosis without Lean (contract §1): the site (or the skip reason), every construct considered and skipped with its
    reason, and the candidates that would be generated."""
    source = (ctx or {}).get("source")
    info = sites(proof, statement, source)
    cands = generate(proof, statement, info=info, source=source) if info.get("fire") else []
    plans = plans_of(info) if info.get("fire") else []
    return {"ok": True, "fire": bool(info.get("fire")), "why": info.get("why"), "rel": info.get("rel"), "shape": info.get("shape"),
            "chain": info.get("chain"), "strengthen": [s["thm"] for s in info.get("strengthen") or []], "own": info.get("own"),
            "inducts": info.get("inducts"), "hyps": info.get("hyps"), "skipped": info.get("skips") or [],
            "uniform_closers": [t for t, _ in uniform_closers(source)],
            "n_probes": len(plans), "n_candidates": len(cands), "first": cands[0]["decl"] if cands else None,
            "sites": [{"op": "t11:template", "rel": info.get("rel"), "plans": [plan_note(p) for p in plans[:8]]}] if info.get("fire") else []}
