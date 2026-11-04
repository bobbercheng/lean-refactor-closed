KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for putnam_1964_a4
- Union best (a landmark reached by another line — your proofs are your own): 96.32 from the GPT Astra line (cxline-astra-normalize1), 147 tokens, 3056 heartbeats.
- Each line's best: Opus 5.5 line 94.4, GPT Astra line 96.32, Flash line 91.3.
- Exchange rate on this problem: 1 token = 0.019 points, 100 heartbeats = 0.030 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
... (262 tokens, 2209 hb), compiles on v4.27/26/25. candidate.lean holds it.

Proof structure (works):
- pigeonhole: `(Set.finite_Icc (B,B,B,B) (T,T,T,T)).exists_lt_map_eq_of_forall_mem (f := fun n => (u n, u (n+1), u (n+2), u (n+3))) fun n => by simp only [Set.mem_Icc, Prod.mk_le_mk, hB, and_self]` (Prod.le_def also works, same cost)
- invariant `key : ∀ m, 4-tuple of equalities at i+m / j+m` by `Nat.recAux (by simpa using h) fun m ih => ...`
  step: h1/h2 := (hu (i+m+4) le_add_self).1 ; `simp only [ih, Nat.reduceSubDiff, add_tsub_cancel_right, ← add_assoc, true_and] at h1 h2 ⊢`; `exact_mod_cast h1.trans h2.symm`
- final: `exact ⟨i, j - i, Nat.sub_pos_of_lt hij, fun n hn => by rw [← Nat.add_sub_cancel' hn, (key _).1, Nat.add_right_comm, Nat.add_sub_cancel' hij.le]⟩`

Run 4 wins: `Nat.recAux` (motive uses `n + 1`, no `Nat.succ_eq_add_one` needed, no `fun m => m.`) : 267→262 tok.
Run 4 neutral/worse: `at *` instead of `at h1 h2 ⊢` (−2 tok, +136 hb, net −0.01). `Nat.rec` without `fun m => m.` works too (needs succ_eq_add_one).
Earlier failures: `exact Int.cast_injective (...)` (+3 tok, −18 hb); `simp [Prod.le_def, hB]` (+2000 hb).
Rule of thumb: 1 token ≈ 0.019 score, 100 hb ≈ 0.03 score.
Ideas not tried: tuple-equality form of key (base case would be just `h`, but est. +5 tokens net).
Note: Bash in this env rejects compound commands (&&, sed -i, heredoc) — use Write tool for edits.
- GPT Astra line notes (tail):
...] -> compiles but adds tokens without heartbeat savings.]
[tested: clearing hu between simp passes -> saves only 4 heartbeats, adds two tokens.]
[tested: combining passes into simp (disch := omega) only [Nat.add_sub_assoc, ih, hu] -> 164 tokens / 4,270 heartbeats before later syntax reductions, lower score.]
[tested: single simp specialized to hu (i + m), hu (j + m) -> compiles at 160 tokens / 3,095 heartbeats when baseline was 158 / 3,059, worse.]
[tested: +arith in place of the omega discharger in both passes or just the second -> simp makes no progress.]
[tested: removing only from first simp -> 151 tokens / 3,324 heartbeats, lower score.]
[tested: removing only from second simp -> 151 tokens / 5,284 heartbeats, lower score.]
[tested: grind only [hu, Nat.add_sub_assoc, ih] -> redundant local hypothesis parameter error.]
[tested: grind only [Nat.add_sub_assoc] -> did not complete after roughly two minutes; terminated Lean, no successful proof or heartbeat measurement.]

Saved files:
incoming174.lean is the incoming proof. saved152.lean, candidate.lean and harness-maintained best.lean contain the final best proof.
The harness requires /home/user/.elan/bin on PATH.

Possible future direction: a cheaper recurrence congruence proof or different finite-state formulation. No claim of optimality; the current best improvements came from ordinary binder and tactic syntax reductions.

