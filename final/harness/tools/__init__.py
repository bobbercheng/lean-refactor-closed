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
)
