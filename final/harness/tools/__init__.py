"""Generic CPU search tools for the end stage (docs/tools_build_plan.md). Each module listed in MODULES implements OPS, TABLES and
candidates(proof, statement, *, exchange=None, max_per_op=40, ctx=None) -> [{"op", "decl", "note"}] (the harness/sweep.candidates
contract, accepted by harness/endstage.sweep_items). The other scripts in this directory are agent CLI tools, not modules of this list.
One line per module; builders add their own line."""
MODULES = (
    "t1_compress",
    "t2_schedule",
    "t3_reclose",
    "t4_nameless",   # opt-in (endstage FAMILIES "t4"), not adopted: verify on held-out finals first
    "t5_joint",      # opt-in (endstage FAMILIES "t5", b63 D): joint multi-site edits searched on the workbench; not in r4_frozen.json
    "t6_transpile",  # endstage FAMILIES "t6" (b63 item 13, r6; harness/tools/famkit.py is its helper, not a tool): nameless transpiler + exists / Exists.imp rules on the workbench
    "t7_defer",      # endstage FAMILIES "t7" (b63 item 15, r7 under bar A): defer side goals / let-collapse / specialised swaps, chained, on the workbench
    "t8_pin",        # endstage FAMILIES "t8" (b63 T10 + item 10, r7 under bar A): instance pins / transparency closers / binder bridges (tables instances, relations)
    "t11_template",  # endstage FAMILIES "t11" (b63 T10 + item 11, r7 under bar A): relation templates from the relation table + uniform closers
    "golf_ops",      # endstage FAMILIES "golf" (b65, docs/argon_review_value.md item 3): trailing-argument drop, case' unwrap, refine -> use, dot notation, have-fun binders; every op opt-in
    "c2_lemvar",     # endstage FAMILIES "c2" (b71 R2, a FINAL family): class-namespace lemma variants (env query + workbench screen) + a compile-gated stack
    "d3_grind",      # bet D3 (bet-backend-replay): family "grindmin", registered only by harness/end_ops.register() (router --end-ops on): grind hint lists compacted
    "d3_simpconst",  # bet D3: family "simpconst" (QUERY_FAMILIES), registered only by harness/end_ops.register(): a simp-list literal -> a named constant Lean finds equal
    "d4_implied",    # bet D4: family "implied" (QUERY_FAMILIES), registered only by harness/end_d4.register(): a decide closer decides a library implication's hypothesis (point-free: D4P opt-in)
    "d4_inlineeq",   # bet D4: family "inlineeq" (QUERY_FAMILIES), registered only by harness/end_d4.register(): an inline proved equation in a simp list -> its hint instantiated
    "d4_search",     # bet D4: family "searchinline" (QUERY_FAMILIES), registered only by harness/end_d4.register(): a search tactic -> Lean's own suggestion
    "d4_lex",        # bet D4: family "primeglue", registered only by harness/end_d4.register(): a prime-ended notation token joined to the next word
    "d4_micro",      # bet D4: family "micro", registered only by harness/end_d4.register(): simp/norm_num head swaps, rw -> simp only, congr swaps, by-argument unnesting
    "d4_closerprep", # bet D4C: family "closerprep", registered only by harness/end_d4.register(["closerprep"]) (router --end-d4-closerprep on): `conv_rhs => reduce` before a decide closer + a simp-list ddmin
    "d4_simpnorm",   # bet D4N: family "simpnorm" (QUERY_FAMILIES), registered only by harness/end_d4.register(["simpnorm"]) (router --end-d4-simpnorm on): generic normalisation lemmas appended to a simp list
)   # (harness/tools/d4_kit.py is the D4 families' helper, not a family)
