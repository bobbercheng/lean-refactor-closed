#!/usr/bin/env python3
"""Leak scan (B62a; 2026-10-20).

Dev-time gate, not shipped data: every deny list below is built at run time from the dev repository's own warm-up material and is never
written into this file, so the scan itself carries no warm-up content. It reads every string the pipeline can put in front of a model
(string literals and f-string text of the modules reachable from the pipeline entry points; docstrings and comments excluded, they never
reach a model) and fails on:
  name      a warm-up row name or a distinctive component of one (e.g. a namespace or the theorem's own name)
  local     an identifier that occurs in the warm-up statements or seed proofs and in no other dataset's (a problem-local name)
  number    a warm-up reference value (proof tokens; official, local or direct-path reference heartbeats) or one of our official per-row scores,
            in plain or thousands-separated form
  lemma     a won lemma: a library-style identifier in our warm-up proofs (uploads, union bests, golf rounds, main-line bests) that occurs in
            no seed proof of any dataset
  lemma'    a dotted suffix of a won lemma (`fun_deriv_sub` of `Space.fun_deriv_sub`), when it is no seed identifier (review 2026-10-21)
  fragment  a run of >= FRAG lexer tokens copied from our warm-up proofs that occurs in no seed proof
  move      a short run (SHORT lexer tokens) inside a code span (backticks) or a Lean-code string of a rule table that occurs in the proofs
            of exactly ONE warm-up row and in no seed: a row's winning move, however generic its words (review 2026-10-21)
  stat      in the knowledge modules (cards, pattern cards, the agent prompts): a measured quantity, a number followed by a heartbeat, token,
            point or percent unit; harness parameters (timeouts, turn and check counts) are not followed by those units
A hit is waived only through ALLOW (generic vocabulary, with a reason). The B30 package check runs the same scan over the export.
Coverage (review 2026-10-22): the closure follows import statements AND modules loaded by name (a string constant that names a module
file, e.g. endstage.FAMILIES[*]["module"] given to importlib, and the bare module names of a package __init__ such as harness/tools MODULES).
The generated tables of the end-stage tools (TABLE_GLOBS) are scanned too, every string key and value; a hit in a table that states how
it was generated ("rule", "query", "generated_at") is reported as waived with that rule as its reason (it is read, not failed); a hit in a
table without them fails.

    python3 harness/leak_scan.py              # report, exit 1 on any hit
    python3 harness/leak_scan.py --json       # machine-readable hits
    python3 harness/leak_scan.py --self-test  # the detectors on synthetic strings
Without the dev material (a fresh clone of the package) the deny lists are empty and the scan says so (status "skipped")."""
from __future__ import annotations

import argparse, ast, glob, json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scorer.tokenize import tokens as lex  # noqa: E402

ENTRY = ["harness/agent.py", "harness/router.py", "harness/hx_heldout.py", "harness/postpass.py", "harness/review.py", "harness/autobrief.py",
         "harness/hb_tool.py", "harness/golf.py", "harness/prompt_v2.py",   # prompt_v2: hx_heldout launches the v2 driver as a subprocess
         "harness/sweep.py",      # B62b end-stage sweep (2026-10-21): scanned before a caller imports it
         "harness/endstage.py",   # B62b end stage (2026-10-21): its labels, notes and decision reasons reach logs and the run dir
         "harness/tools/__init__.py",   # end-stage tool modules (MODULES), loaded by name through endstage.FAMILIES (review 2026-10-22)
         # b66 closed package (2026-10-27): the organizers' one command, its row loader / merge / host knobs and the rehearsal's fake model
         "infra/closed_package/run_final.py", "infra/closed_package/envs_from_rows.py", "infra/closed_package/fake_openrouter.py"]
# generated data tables of the end-stage tools: every string is scanned (the per-table waiver is the table's own generating rule)
TABLE_GLOBS = ("harness/tools/tables/*.json",)
TABLE_META = ("rule", "query", "generated_at")
# dev-only drivers and tools that the final configuration never imports (docs/port_compliance.md section I); excluded from the closure
# (cc_levers, discover and transfer are NOT here: inrun.py and hx_heldout.py import them on the live path)
DEV_ONLY = {"harness/agent_claude_code.py", "harness/agent_codex.py", "harness/agent_opencode.py", "harness/exemplars.py",
            "harness/kimi_bridge.py", "harness/leak_scan.py"}
# modules whose strings are knowledge for the model: measured quantities are not allowed there at all
KNOWLEDGE = {"harness/cards.py", "harness/pattern_cards.py", "harness/agent.py", "harness/golf.py", "harness/architect.py", "harness/review.py",
             "harness/autobrief.py", "harness/inrun.py"}
FRAG = 8
SHORT = 4
IDENT = re.compile(r"[^\W\d][\w'!?₀-₉ₛₗ]*(?:\.[^\W\d][\w'!?₀-₉ₛₗ]*)*")
STAT = re.compile(r"(?<![\w.])(\d[\d,.]*)\s*(?:k\b|K\b)?\s*(?:-|–|to)?\s*(?:\d[\d,.]*)?\s*(?:hb\b|heartbeats?\b|tokens?\b|points?\b|pts\b|%)")
# generic vocabulary that the lemma / local scans may meet in prompts; each entry is general Lean/Mathlib, not a warm-up move
ALLOW = {
    # tactics and keywords (general Lean syntax)
    "solve_by_elim", "exact_mod_cast", "fun_induction", "fun_prop", "with_reducible", "nofun", "nomatch", "any_goals", "all_goals",
    "simp_all", "simp_rw", "simp_arith", "norm_num", "field_simp", "push_cast", "split_ifs", "by_cases", "by_contra", "rintro", "rcases",
    "obtain", "refine", "exact", "apply", "intro", "constructor", "assumption", "contradiction", "linarith", "nlinarith", "positivity", "omega",
    "grind", "aesop", "decide", "simpa", "calc", "suffices", "show", "generalize", "induction", "cases", "match", "first", "repeat", "try",
    "maxDischargeDepth", "disch", "linear_combination", "gcongr", "bound", "Elab.async", "set_option", "rotate_left", "rotate_right",
    "nth_rewrite", "nth_rw", "trace_state", "push_neg", "pick_goal", "beta_reduce", "subst_vars", "apply_rules", "apply_rfl",
    "with_unfolding_all", "with_reducible_and_instances", "pp.proofs", "pp.fullNames", "IO.getNumHeartbeats", "Classical.choice", "Exists",
    "econstructor", "conv_lhs", "conv_rhs", "rename_i", "exacts", "introv", "fin_cases", "interval_cases", "unhygienic", "haveI", "by_contra!",
    "ENat", "biUnion", "simp_all!",   # b84: simp_all! (Lean core's tactic, as by_contra! above) is named by harness/approach_pick.py's filter
    # 2026-10-25 (b63 launch set, item 19; docs/adaptive_plan_93.md §4.1): the core `assumption'` tactic (assumption modulo reducible defeq),
    # a general Lean move like unhygienic / econstructor above; a move gram made only of ALLOW words and punctuation is syntax, not a row's move
    "assumption'",
    # b85 (docs/b85_style_rw.md): core Lean names the style_rw dialect guide names on purpose (pre-shaping with `.imp` instead of
    # destructuring): Init's And.imp / Exists.imp / Or.imp are general syntax-level moves, no row's lemma (b80's leak guard GENERAL set)
    "And.imp", "Exists.imp", "Or.imp",
    # the generic bundled-hom lemma family that hb_rewrite's specialize operator looks for in a proof (its inputs, not a dev row's move)
    "map_add", "map_sub", "map_zero", "map_neg", "map_sum", "map_mul", "map_one", "map_pow", "map_smul",
    # generic projection / method names (dot notation on any term)
    "trans_eq", "trans_lt", "trans_le", "resolve_left", "resolve_right", "symm", "mp", "mpr",
    # core logic and data structures every proof uses
    "Or.inl", "Or.inr", "Or.imp", "And.intro", "Exists.intro", "absurd", "False.elim", "id", "rfl", "trivial", "Nonempty",
    # core logic lemmas written by t6_transpile's shape-driven Exists.imp / choose rules (b63 item 13; the goal's shape `∃ x, A ∧ R .. x`
    # decides, never a name): the same class as Or.imp / And.intro above
    "Exists.imp", "And.imp_right", "And.imp_left",
}


def _jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.open() if l.strip()] if p.exists() else []


def _walk_proofs(obj, out: list) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "proof" and isinstance(v, str):
                out.append(v)
            else:
                _walk_proofs(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _walk_proofs(v, out)


def _decl_only(text: str) -> str:
    """A golf file can carry the measuring prelude or a file header before the declaration: keep the declaration only."""
    if "arena_measure" in text:
        text = text[text.rfind("arena_measure"):].partition("\n")[2]
    m = re.search(r"^(?:private |protected )?(?:theorem|lemma) ", text, re.M)
    return text[m.start():] if m else text


def _safe(n: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", n)


def deny_lists(root: Path = ROOT) -> dict:
    """Everything the scan looks for, computed from the dev repository (empty sets without it)."""
    rows = _jsonl(root / "data/benchmark_warmup.jsonl")
    names = {r["name"] for r in rows}
    other = _jsonl(root / "data/heldout/heldout.jsonl") + _jsonl(root / "data/abpool/abpool.jsonl")   # non-warm-up seeds (sealed sets untouched)
    seeds = [r.get("src") or "" for r in rows + other]
    # name: full names and distinctive components (namespaces and theorem names of the warm-up rows; a few generic words skipped)
    comp = set()
    for n in names:
        for c in n.split("."):
            if len(c) >= 4 and c not in {"Core", "Cslib", "progress", "Binius", "putnam"}:
                comp.add(c)
    name_terms = names | comp
    # local: identifiers of the warm-up statements and seeds that no other dataset uses, library-style only (capitalised, dotted, or with _)
    ids_wu = set().union(*(set(IDENT.findall((r.get("statement") or "") + "\n" + (r.get("src") or ""))) for r in rows)) if rows else set()
    ids_other = set().union(*(set(IDENT.findall((r.get("statement") or "") + "\n" + (r.get("src") or ""))) for r in other)) if other else set()
    local = {i for i in ids_wu - ids_other if re.search(r"[a-z][A-Z]|^[A-Z]{2,}[a-z]|[._]", i) and len(i) >= 3 and i not in ALLOW}
    # number: reference values and our official per-row scores
    nums = set()
    for r in rows:
        nums.add(int(r["proof_length"]))
    hbs = {r["name"]: r["heartbeat"] for r in _jsonl(root / "data/benchmark_heartbeats.jsonl")}
    nums |= {int(hbs[n]) for n in names if hbs.get(n)}
    loc = json.loads((root / "data/reference_heartbeats_local.json").read_text()) if (root / "data/reference_heartbeats_local.json").exists() else {}
    nums |= {int((loc.get(n) or {}).get("heartbeats_local") or 0) for n in names} - {0}
    rd = root / "probe/calib/ref_direct.json"
    if rd.exists():
        nums |= {int(v) for k, v in json.loads(rd.read_text()).items() if k in names and isinstance(v, (int, float))}
    number_terms = {s for n in nums if n >= 100 for s in (str(n), f"{n:,}")}
    # our official per-row scores; 33.33 (= 100/3, the score of any unchanged reference proof) is not row-specific
    for wf in glob.glob(str(root / "submit/results/*.worker.json")):
        try:
            for e in json.loads(Path(wf).read_text()):
                if isinstance(e, list) and len(e) > 2 and e[0] in names:
                    s = str(e[2]).rstrip("%").strip()
                    if re.fullmatch(r"\d{2,3}\.\d+", s) and s != "33.33":
                        number_terms.add(s)
        except Exception:  # noqa: BLE001
            pass
    # ours: every warm-up proof we produced
    ours: list[str] = []
    for f in glob.glob(str(root / "submit/candidates/*.jsonl")):
        ours += [r["proof"] for r in _jsonl(Path(f)) if r.get("name") in names and r.get("proof")]
    for f in glob.glob(str(root / "probe/review/union_bests*.json")) + [str(root / "probe/calib/rerank_candidates.json")]:
        if Path(f).exists():
            _walk_proofs(json.loads(Path(f).read_text()), ours)
    for pat in ("probe/golf93*/**/*.lean", "probe/bank_discards/**/*.lean"):
        ours += [_decl_only(Path(f).read_text()) for f in glob.glob(str(root / pat), recursive=True)]
    for n in names:
        ours += [Path(f).read_text() for f in glob.glob(str(root / "harness" / "work*" / _safe(n) / "best.lean"))]
    seed_ids = set().union(*(set(IDENT.findall(s)) for s in seeds)) if seeds else set()
    stmt_ids = set().union(*(set(IDENT.findall(r.get("statement") or "")) for r in rows + other)) if rows else set()
    our_ids = set().union(*(set(IDENT.findall(p)) for p in ours)) if ours else set()
    lemma = {i for i in our_ids - seed_ids - stmt_ids - ALLOW if ("." in i or "_" in i or i[:1].isupper()) and len(i) >= 5}
    suffix = set()
    for i in lemma:
        parts = i.split(".")
        for k in range(1, len(parts)):
            t = ".".join(parts[k:])
            if len(t) >= 6 and re.search(r"_|[a-z][A-Z]", t) and t not in seed_ids and t not in ALLOW:
                suffix.add(t)
    lemma |= suffix
    # fragment: lexer n-grams of our proofs absent from every seed
    def grams(t: list[str]) -> set:
        return {tuple(t[k:k + FRAG]) for k in range(len(t) - FRAG + 1)}
    seed_g = set().union(*(grams(lex(s)) for s in seeds)) if seeds else set()
    frag = set().union(*(grams(lex(p)) for p in ours)) - seed_g if ours else set()
    # move: SHORT-grams in the proofs of exactly one warm-up row, in no seed (rows taken from the files that name them)
    by_row: dict = {}
    def add_row(n, text):
        if n in names and text:
            by_row.setdefault(n, set()).update(_grams(lex(text), SHORT))
    for f in glob.glob(str(root / "submit/candidates/*.jsonl")):
        for r in _jsonl(Path(f)):
            add_row(r.get("name"), r.get("proof"))
    for f in glob.glob(str(root / "probe/review/union_bests*.json")):
        try:
            for n, v in json.loads(Path(f).read_text()).items():
                add_row(n, (v or {}).get("proof") if isinstance(v, dict) else None)
        except Exception:  # noqa: BLE001
            pass
    for n in names:
        for f in glob.glob(str(root / "harness" / "work*" / _safe(n) / "best.lean")):
            add_row(n, Path(f).read_text())
    seed_s = set().union(*(_grams(lex(s), SHORT) for s in seeds)) if seeds else set()
    cnt: dict = {}
    for n, g in by_row.items():
        for x in g:
            cnt[x] = cnt.get(x, 0) + 1
    move = {x for x, c in cnt.items() if c == 1 and x not in seed_s and sum(1 for t in x if re.search(r"[^\W\d_]", t)) >= 2   # punctuation-only: syntax
            and any(re.search(r"[^\W\d_]", t) and t not in ALLOW for t in x)}   # item 19: all-ALLOW words (`any_goals constructor assumption'`) are syntax
    return {"name": name_terms, "local": local, "number": number_terms, "lemma": lemma, "fragment": frag, "move": move,
            "sizes": {"rows": len(rows), "our_proofs": len(ours), "name": len(name_terms), "local": len(local), "number": len(number_terms),
                      "lemma": len(lemma), "fragment": len(frag), "move": len(move)}}


def _grams(t: list, n: int) -> set:
    return {tuple(t[k:k + n]) for k in range(len(t) - n + 1)}


_SPAN = re.compile(r"`([^`]+)`")
_CODELIKE = re.compile(r"^\s*(?:[a-z_][\w']*(?:\?|!)?)(?:\s|$)")   # a string that starts like a tactic line (rule-table entries)


def code_spans(text: str) -> list[str]:
    """Lean code inside a string: backtick spans, or the whole string when it reads as tactic code (no sentence punctuation)."""
    spans = _SPAN.findall(text)
    if not spans and _CODELIKE.match(text) and not re.search(r"[.!?]\s+[A-Z]", text) and len(text) < 400:
        spans = [text]
    return spans


_MODNAME = re.compile(r"(?:harness|scorer|llm|probe)(?:\.[A-Za-z_]\w*)+")
_BARE = re.compile(r"[A-Za-z_]\w*")


def closure(root: Path = ROOT, entry=ENTRY) -> list[str]:
    """Modules reachable from the entry points through any import statement (lazy imports inside functions included) or by name: a string
    constant that names a module file (`"harness.tools.t2_schedule"` given to importlib), and in a package __init__ a bare string naming
    a sibling module (harness/tools MODULES). Importing a package module runs the package's __init__, so that is followed too."""
    todo = [e for e in entry if (root / e).exists()]; seen: set = set()
    while todo:
        f = todo.pop()
        if f in seen or f in DEV_ONLY:
            continue
        seen.add(f)
        init = str(Path(f).parent / "__init__.py")
        if Path(f).name != "__init__.py" and Path(f).parent != Path(".") and (root / init).exists():
            todo.append(init)
        try:
            tree = ast.parse((root / f).read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            mods = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module] + [f"{node.module}.{a.name}" for a in node.names]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                if _MODNAME.fullmatch(node.value):   # a module loaded by name
                    mods = [node.value]
                elif Path(f).name == "__init__.py" and _BARE.fullmatch(node.value):   # a package's own module list
                    sib = str(Path(f).parent / (node.value + ".py"))
                    if (root / sib).exists():
                        todo.append(sib)
            for m in mods:
                if m.split(".")[0] in ("harness", "scorer", "llm", "probe"):
                    p = m.replace(".", "/") + ".py"
                    if (root / p).exists():
                        todo.append(p)
                elif (root / "harness" / (m + ".py")).exists():   # router's `import hx_heldout as H` (harness on sys.path)
                    todo.append(f"harness/{m}.py")
    return sorted(seen)


def table_files(root: Path = ROOT) -> list[str]:
    return sorted({str(Path(g).relative_to(root)) for pat in TABLE_GLOBS for g in glob.glob(str(root / pat))})


def table_strings(obj, out: list | None = None) -> list[str]:
    """Every string of a JSON table, keys included (a table keyed by token names carries its entries in its keys)."""
    out = [] if out is None else out
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k)); table_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            table_strings(v, out)
    return out


def table_waiver(tab) -> str | None:
    """The waiver reason of a generated table: its own generating rule, when it states rule, query and generated_at; else None."""
    if isinstance(tab, dict) and all(isinstance(tab.get(k), str) and tab.get(k).strip() for k in TABLE_META):
        return "table rule: " + re.sub(r"\s+", " ", tab["rule"])[:200]
    return None


def strings(path: Path) -> list[tuple[int, str]]:
    """(line, text) of every string literal and f-string, docstrings excluded; f-string fields become {}."""
    tree = ast.parse(path.read_text())
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            b = node.body[0]
            if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                docs.add(id(b.value))
    src = path.read_text().split("\n")
    for node in ast.walk(tree):   # never shown to a model: argparse help texts and print() / log lines
        if isinstance(node, ast.keyword) and node.arg == "help":
            docs |= {id(n) for n in ast.walk(node.value)}
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
            docs |= {id(n) for a in node.args for n in ast.walk(a)}
    for node in ast.walk(tree):   # waiver: a `leak-ok: <reason>` comment on the string's own lines (harness parameters, lexer facts)
        if isinstance(node, (ast.Constant, ast.JoinedStr)) and any("leak-ok:" in l for l in src[node.lineno - 1:(node.end_lineno or node.lineno)]):
            docs |= {id(n) for n in ast.walk(node)}
    out = []; inner = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr) and id(node) not in docs:
            txt = "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "{}" for v in node.values)
            out.append((node.lineno, txt))
            inner |= {id(v) for v in node.values}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in inner:
            out.append((node.lineno, node.value))
    return out


def _word_hit(term: str, text: str) -> bool:
    return re.search(r"(?<![\w.'])" + re.escape(term) + r"(?![\w'])", text) is not None


def scan_text(text: str, D: dict, knowledge: bool) -> list[tuple[str, str]]:
    hits = []
    ids = set(IDENT.findall(text))
    for cat in ("name", "local", "lemma"):
        for t in sorted(D[cat] & ids if cat != "name" else {t for t in D[cat] if _word_hit(t, text)}):
            hits.append((cat, t))
    for t in sorted(D["number"]):
        if re.search(r"(?<![\d.,])" + re.escape(t) + r"(?![\d])", text):
            hits.append(("number", t))
    if D["fragment"]:
        toks = lex(text)
        for k in range(len(toks) - FRAG + 1):
            g = tuple(toks[k:k + FRAG])
            if g in D["fragment"]:
                hits.append(("fragment", " ".join(g)))
                break
    if D.get("move"):
        for sp in code_spans(text):
            g = _grams(lex(sp), SHORT) & D["move"]
            if g:
                hits.append(("move", " ".join(sorted(g)[0])))
    if knowledge:
        for m in STAT.finditer(text):
            hits.append(("stat", m.group(0).strip()))
    return hits


def scan(root: Path = ROOT, D: dict | None = None, files: list[str] | None = None, tables: list[str] | None = None) -> dict:
    """files: modules to scan (default: the closure); tables: JSON tables to scan (default: TABLE_GLOBS when files is the default, none
    when files are given). A table hit is waived (listed under "waived", not failed) when the table states its generating rule."""
    D = D or deny_lists(root)
    if tables is None:
        tables = table_files(root) if files is None else []
    files = files or closure(root)
    hits, waived = [], []
    for f in files:
        for line, txt in strings(root / f):
            for cat, term in scan_text(txt, D, f in KNOWLEDGE):
                hits.append({"file": f, "line": line, "cat": cat, "term": term, "context": re.sub(r"\s+", " ", txt)[:160]})
    for f in tables:
        try:
            tab = json.loads((root / f).read_text())
        except (OSError, ValueError) as e:
            hits.append({"file": f, "line": 0, "cat": "table", "term": type(e).__name__, "context": "unreadable table"})
            continue
        why = table_waiver(tab)
        for txt in dict.fromkeys(table_strings(tab)):
            for cat, term in scan_text(txt, D, False):
                h = {"file": f, "line": 0, "cat": cat, "term": term, "context": re.sub(r"\s+", " ", txt)[:160]}
                if why:
                    waived.append(h | {"waiver": why})
                else:
                    hits.append(h)
    status = "skipped" if not D["sizes"]["our_proofs"] else ("pass" if not hits else "fail")
    return {"status": status, "files": files, "tables": tables, "sizes": D["sizes"], "hits": hits, "waived": waived}


def self_test() -> int:
    D = {"name": {"fooRow"}, "local": {"MyRel"}, "number": {"12345", "12,345"}, "lemma": {"Foo.bar_baz"},
         "fragment": {tuple(lex("have K : A ⊆ C → B ⊆ D := by grind"))[:FRAG]}, "move": {tuple(lex("any_goals constructor zqfoo_tac x"))[:SHORT]},
         "sizes": {}}
    cases = [("use Foo.bar_baz here", "lemma", True), ("cost 12,345 here", "number", True), ("the fooRow proof", "name", True),
             ("MyRel holds", "local", True), ("have K : A ⊆ C → B ⊆ D := by grind", "fragment", True), ("one set costs ~165 hb", "stat", True),
             ("Timeout 120 s, at most 6 variants", "stat", False), ("use Foo.bar here", "lemma", False), ("cost 123456", "number", False),
             ("try `any_goals constructor zqfoo_tac x` here", "move", True), ("any_goals constructor\n  zqfoo_tac x", "move", True),
             ("try `any_goals constructor assumption' x` here", "move", False),   # item 19: all-ALLOW grams never enter D["move"] (deny_lists)
             ("Write each piece once. Use all_goals.", "move", False)]
    bad = 0
    for txt, cat, want in cases:
        got = any(c == cat for c, _ in scan_text(txt, D, True))
        print(("PASS" if got == want else "FAIL"), cat, repr(txt))
        bad += got != want
    # coverage: modules loaded by name and a package's module list are in the closure; table hits are waived only with a stated rule
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / "harness/pkg/tables").mkdir(parents=True)
        (r / "harness/a.py").write_text('FAM = {"x": {"module": "harness.b"}}\n')
        (r / "harness/b.py").write_text('X = "use Foo.bar_baz"\n')
        (r / "harness/pkg/__init__.py").write_text('MODULES = ("c",)\n')
        (r / "harness/pkg/c.py").write_text('Y = "plain"\n')
        (r / "harness/pkg/d.py").write_text('Z = "not listed"\n')
        got = closure(r, ["harness/a.py", "harness/pkg/__init__.py"])
        ok = got == ["harness/a.py", "harness/b.py", "harness/pkg/__init__.py", "harness/pkg/c.py"]
        print(("PASS" if ok else "FAIL"), "closure follows modules loaded by name", got); bad += not ok
        (r / "harness/pkg/tables/ruled.json").write_text(json.dumps({"rule": "r", "query": "q", "generated_at": "t", "forms": {"Foo.bar_baz": 1}}))
        (r / "harness/pkg/tables/bare.json").write_text(json.dumps({"forms": ["Foo.bar_baz"]}))
        res = scan(r, D | {"sizes": {"our_proofs": 1}}, files=["harness/b.py"], tables=["harness/pkg/tables/ruled.json", "harness/pkg/tables/bare.json"])
        ok = ({(h["file"], h["cat"]) for h in res["hits"]} == {("harness/b.py", "lemma"), ("harness/pkg/tables/bare.json", "lemma")}
              and [h["file"] for h in res["waived"]] == ["harness/pkg/tables/ruled.json"])
        print(("PASS" if ok else "FAIL"), "table hits: waived with a rule, failed without"); bad += not ok
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--root", default=str(ROOT))
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    r = scan(Path(a.root))
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(f"leak scan: {r['status']} ({len(r['files'])} modules, {len(r['tables'])} tables; deny lists {r['sizes']})")
        for h in r["hits"]:
            print(f"  {h['cat']:8s} {h['file']}:{h['line']}  {h['term']!r}  | {h['context']}")
        for h in r["waived"]:
            print(f"  waived   {h['cat']:8s} {h['file']}  {h['term']!r}  | {h['context'][:80]}  [{h['waiver'][:100]}]")
        print(f"{len(r['hits'])} hit(s), {len(r['waived'])} waived table hit(s)")
    return 1 if r["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
