KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Cslib.LambdaCalculus.LocallyNameless.Fsub.Typing.progress
- Union best (a landmark reached by another line — your proofs are your own): 88.81 from the Opus 5.5 line (ccline-opus55-bounty1), 109 tokens, 4107 heartbeats.
- Each line's best: Opus 5.5 line 88.81, GPT Astra line 86.05, Flash line 77.93.
- Exchange rate on this problem: 1 token = 0.082 points, 100 heartbeats = 0.056 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...rs it saves). The same trick on tapp would be net +1.
- [tested] Reordering the solve_by_elim list (case_inl, case_inr, let_body, tabs, abs, appᵣ, case): 4581 hb, so order doesn't matter.
- Red ctor order (from #print): appₗ, appᵣ, tapp, abs, tabs, let_bind, let_body, inl, inr, case, case_inl, case_inr.
  The constructor fallback (MVarId.constructor) commits to the first ctor that unifies, so the "later" ctors
  (appᵣ, abs, tabs, let_body, case_inl, case_inr) must be in the list. Not re-tested one by one.
- Typing.wf : Typing Γ t τ → Γ.Wf ∧ t.LC ∧ Wf Γ τ.
- TOOL NOTE: in this sandbox Bash only allows a plain `python3 .../lean_check.py` or `lean_run.py` call. sed -i, `cd x; ...`
  chains, helper scripts, /tmp writes, and grep in the envs/ source tree are all blocked. Edit candidate.lean with Write.
  Use `git show HEAD:./notes.md` to recover notes. (Run 6 overwrote notes.md once by mistake and recovered it this way.)

## Trade-off now
1 token ≈ 0.08 score ≈ 140 hb (hb% is relative to 59830).

## Next ideas
- With `body` hyps in context, the case goals might fit in the default maxDepth (-5 tok), but
  `obtain ⟨-, _, _⟩ := body_case.1 der'.wf.2.1` costs more than that.
- A cheaper way to handle the 4 inl/inr goals (≈1350 hb, mostly the failing Or.inr search on the val branches)
  is the only sizeable hb target left.
- Looks like a local optimum; remaining gains are probably ≤ 0.2.
- GPT Astra line notes (tail):
...ssumption/apply Value.lc/constructor -> failed by choosing incorrect reduction constructors.]
- [tested: omit Exists.intro and all first matching Red constructors -> five failures; restore Exists.intro -> only case reduction failed; restore Red.case -> success.]
- [tested: aesop with safe constructors Red and Value.lc, with body facts present -> failed, 23772 heartbeats.]
- [tested: single final solve_by_elim with Or.inl/Or.inr and default depth -> failed; depth 8 succeeded but scored worse.]
- [tested: only [*] on both shared searches -> saved heartbeats but token overhead scored slightly worse in that version.]
- [tested: restore full explicit Red list in merged224 version -> 230 tokens, 4072 heartbeats, score 78.94, worse than 224-token version.]
- [tested: single final solve_by_elim [Or.inr, ...] in latest proof -> 217 tokens but failed five goals, 10741 heartbeats. Restored merged221.lean.]

Confirmed lemmas: Typing.wf, canonical_form_abs, canonical_form_tabs, canonical_form_sum, body_let, body_case. `cases lc` in application/type application exposes enough closure facts for reductions without Value.lc.

Next ideas: reduce duplicate rcases of induction hypotheses across branches, or tune the shared search without increasing tokens substantially. No claim of optimality.

Environment: lake is not on default PATH. Run prescribed checker with PATH=/home/user/.elan/bin:$PATH.

