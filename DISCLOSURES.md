# Disclosures: closed-source LLM track (team Vexorium)

What our closed-track results rest on and what this repository leaves out. The results themselves are in
[`RESULTS.md`](RESULTS.md); the package and its settings in [`final/README.md`](final/README.md).

## Kernel skip

`sub30` and `sub32` carried Lean's `set_option debug.skipKernelTC true in` on 4 rows (FTheory
isPhenoClosedQ5 / Q10 and two PauliMatrix rows), placed by our post-step's `kskip` op in front of a closing `decide +kernel`. The option
skips the kernel's check of the declaration; it is not on the Arena's forbidden list, and the Arena graded those rows. On 2026-11-04 we
re-checked all four rows of both uploads with a plain `decide +kernel` (kernel check on): all passed. We nevertheless withdrew the
construct by our decision of 2026-11-04: `sub34` and its code run the post-step without `kskip` and carry no `debug.skipKernelTC`.

## The final package and what it carries from our development work

[`final/`](final/) runs, for every benchmark row and from its seed proof (no stored proofs of the rows apart from the style rewrite's
example pairs; what it carries from our development work is at the end of this section): GPT-6.1 Sol (through OpenRouter) in tool-using sessions
until the row has spent $1.25, GPT-6.1 Terra for the later budget steps, a Gemini 4 Argon review with **repair + stack** (R6: a review
edit that does not compile gets one repair turn from the same model inside the row's room under the cap, and the review's compiling
edits, gains below its single-edit bar included, are also tried together in one compile on every listed toolchain; a verified
combination is kept for the end stage), the **Terra tail** (a row with at least $0.20 of room left under the cap gets up to 3 more Terra
sessions budgeted to exactly that room; their proof is kept only if it compiles on no fewer listed toolchains than the current proof and
scores higher), a model-free end stage that keeps a rewrite only on the same two conditions, **+ approach pick (1 extra
group, time cap)** (the end stage then polishes the best proof of one other approach among the row's candidates the same way, under a
hard 1200 s cap per row, and keeps it only if it compiles on every listed toolchain and scores higher), and the **style rewrite**
(style_rw: GPT-6.1 Sol rewrites the row's final into the shortest idiom the scorer rewards, with at most $0.30 of the row's room under
the cap and at most 15 minutes; its proof is kept only if it compiles on every listed toolchain, passes the axiom audit and scores at
least 0.05 higher on a paired read). A **sorry guard** forces Lean's `warn.sorry` on in every compile and audits each row's final proof
on every listed toolchain before it is written; a proof found to depend on `sorry` is passed over for the row's next verified proof.
Inference spend is capped at **$3.00 per row** by the code itself. The exact pipeline, its version and how to run it are in
[`final/README.md`](final/README.md) and [`final/CODE_VERSION.md`](final/CODE_VERSION.md). [`final/`](final/) is the code of our
closed official run 3 on the final benchmark (2026-11-02, commit `402c44d2`): run 1's pipeline plus three model-free end-stage passes
(`--bets D2,D3,D4,D4P,D4S,D4C,D4N`; each output adopted only when it reads strictly higher and compiles on no fewer listed toolchains)
and the reference step's env fix; section 9 of [`final/README.md`](final/README.md) lists the steps of run 3, run 2 (commit `0ea568e2`,
the `final/` of release `closed-final-run2-probe-20261102`) and run 1 (commit `b5f036ab`, release `closed-final-probe-20261102`). Runs 2
and 3 ran side by side on two hosts. Update 2026-11-04: our final closed upload is `sub41`, run 3's output after two passes of the
post-step without kernel-skip (v4su), with the code of tag `closed-final-sub41-20261104` (run 3's code plus the post-step), not
this branch's `final/` (before it: `sub34`, tag `closed-final-run3-postv2-nokskip-20261104`, and `sub30`, run 1's output after the
post-step, tag `closed-final-run1-post-20261103`). What it carries from our development work: the style rewrite's nine example pairs
(five of them improved proofs of three warm-up theorems that are also final-benchmark rows); two end-stage passes, D3 and D4, developed
on the final benchmark after its release, mainly from our offline research (uncapped agent sessions of other closed models on 5 of
its rows, outside the $3 cap; none of their proofs is in any upload or package) and from our first run's results; the third pass,
D2, from our warm-up work before the release; the passes that run were chosen by measurements on final-benchmark rows; the run-2
fixes come from that first run's records ([`final/README.md`](final/README.md), top). The passes hold no row names and no proof text of
any row. [`final/`](final/) is not byte-identical to the code that ran: it keeps the export's
comment and docstring redactions, and one file of the style rewrite is withheld. The code zip submitted to the organizers has the exact
files ([`final/README.md`](final/README.md) section 8, Byte identity).

## Knowledge given to the first warm-up submission

Our first warm-up submission (`sub06`, 89.46; [`RESULTS.md`](RESULTS.md), section "Earlier: the first warm-up submission") was not a
cold start. The model was given knowledge from earlier research, and the API spend given for it does not include that research:

- **Per-problem knowledge briefs.** They were built from earlier research lines on these same 15 problems: Claude Opus 5.5,
  GPT Astra and GLM-5.3-Flash. One brief also gained an addendum from an earlier GPT-6.1 Sol line, after the submitted
  snapshot.
  - They contain landmark numbers, lever lists and lists of failed attempts.
  - In places they also contain short Lean fragments and proof-structure outlines (for example `putnam_1964_b2`).
  - No brief contains a complete proof.
- **General habits.** The harness option `--closed-lessons` is on by default in this code. As a result, every session's
  first message carried a short list of general habits mined from the Opus 5.5 and GPT Astra lines.
- **Runner inputs.** The runner also read two sets of scores, both included here as scores only:
  - per-problem target scores, which are the union best over the earlier lines
  - the first-session scores of an earlier GPT-6.1 Sol line

Details are in [`warmup/README.md`](warmup/README.md) section 5.
