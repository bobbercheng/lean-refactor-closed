# Notices

Our own code, notes, logs and run records in this repository are licensed under the PolyForm Noncommercial License 1.0.0
(see [`LICENSE`](LICENSE)): free for study, research and other noncommercial use. Commercial use needs a separate license:
contact b.cheng@vexorium.net.

The following material was not written by us. It keeps its own terms, and the license above does not cover it.

| Material | Where | Terms |
|---|---|---|
| Lean source files of upstream libraries (ArkLib, Strata, cslib, PhysLean), copied as problem context | `**/context.lean` and copies of them under `states/`, `hwork/` and in run trajectories | the upstream projects' licenses; the copied files keep their copyright headers (Apache 2.0 where stated) |
| Mathlib, read to generate lookup tables | `final/harness/tools/tables/` | Mathlib's license (Apache 2.0) |
| Competition problems, seed proofs, reference proofs and heartbeat data (incl. PutnamBench statements) | `**/data/benchmark_*.jsonl`, `**/reference_heartbeats*.json`, problem statements and seed proofs in run records | the competition organizers' and the original sources' terms |
| Model outputs (GPT-6.1 Sol, Gemini 4 Argon, GPT-6.1 Terra and others) | run trajectories and logs | recorded as produced; the model providers' terms apply |

## Edits for public release (2026-10-28)

The history of this repository was rewritten on 2026-10-28, before it was made public. Every commit keeps its date and content,
except:

- home-directory paths read `/home/user` (also in logs and trajectories), and the user name in `ls -l` output reads `user`;
- internal notes were removed from comments, docstrings, help texts, docs and logs, and seven internal planning notes under
  `warmup/autobrief_20261014/docs/` were deleted; the code's behaviour is unchanged (same syntax tree apart from
  help-text strings, one log message and development-only paths), with one exception: the development-only Vertex AI path reads its GCP project from the
  environment variable `LRA_GCP_PROJECT` instead of a literal (the final pipeline calls OpenRouter and never uses Vertex);
- model-facing prompts and recorded trajectories are unchanged apart from paths.

## Edits for public release (2026-11-01)

- **Withheld file.** `final/harness/style_rw_exemplars.json` (sha256 `c03ffd730e950d93...`), the style rewrite's nine example proof
  pairs, was removed from the tree. The organizers receive it in the submitted code zip. Without it, `final/` cannot replicate the
  style rewrite step ([`final/README.md`](final/README.md), the style rewrite).
  On 2026-11-01 the history was rewritten again to remove the file from every commit (it was added on 2026-10-30 with the first
  `final/`); every commit from that one on has a new id.
- **`final/` is a staged export.** Its code differs from the commit of the run it holds (closed official run 2, `0ea568e2`; run 1's `b5f036ab` before 2026-11-02) only by the comment, docstring, help-text and
  message edits, the end-stage configuration's documentation keys and the export `.gitignore` listed in
  [`final/CODE_VERSION.md`](final/CODE_VERSION.md) (Staging edits), and by the withheld file above. Among those edits, the
  development-only Vertex AI path reads its GCP project from `LRA_GCP_PROJECT` (the final never uses Vertex). The submitted code zip has
  the exact files of that commit; [`final/README.md`](final/README.md) section 8 (Byte identity) gives the file counts.
- **Code left as it ran.** Code under `final/` (anything the pipeline executes or reads) was not edited for this release, apart from the
  removal above, and neither were the code and run records under `warmup/`. So a few internal traces stay in them: one line of the
  model-facing system prompt cites an internal design decision by role and date (the prompts are unchanged), and two code comments use
  internal log wording. The docstrings of the D4 tools say the tools hold no lemma names: they mean no row-specific names; the few
  fixed generic names they write are listed at the top of `final/README.md`.
- **Corrected documents.** `README.md`, `final/README.md` and `final/CODE_VERSION.md`: the list of our closed-track uploads (two were
  missing), the byte-identity statement for `final/` (it said "exactly the code"), the source of the style rewrite's example pairs (they
  were described as proofs of other theorems only), the contents of `final/` and the credentials it takes.
- **Provenance of the end-stage passes (2026-11-02).** `README.md`, `final/README.md`, `final/CODE_VERSION.md`, `warmup/README.md` and
  `warmup/AUTOBRIEF.md` (a dated note): two of the end-stage passes of closed run 2 were developed on the final benchmark (our offline
  research on 5 of its rows and our first run's results), and the passes that run were chosen by measurements on final-benchmark rows.
  The first text of 2026-11-02 said the package used no per-problem knowledge apart from the style rewrite's examples. The same
  correction fixes two more earlier statements: R2 and R3 were described as tested (they were skipped without a test), and the
  passes' fixed library names were understated (the top of `final/README.md` lists them).
- **`warmup/README.md`.** `warmup/` holds records as they ran. Only the opening section of its README was edited (the submission
  heading and the description of `../final/`), and `AUTOBRIEF.md` got a dated note (2026-11-02).
