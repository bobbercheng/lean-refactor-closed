KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for Binius.BinaryBasefold.fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius
- Union best (a landmark reached by another line — your proofs are your own): 92.27 from the Opus 5.5 line (ccline-opus55-normalize1), 178 tokens, 1766 heartbeats.
- Each line's best: Opus 5.5 line 92.27, GPT Astra line 88.39, Flash line 82.52.
- Exchange rate on this problem: 1 token = 0.023 points, 100 heartbeats = 0.213 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
...Profile (run 6, #count_heartbeats w/ `set_option Elab.async false in` before it — REQUIRED, else only header counted)
header/statement 490; sInf_mem+binder 200; ENat front (mul_le_mul_of_nonneg_left+distFromCode+trans_lt+coe_lt_coe.2) 180;
Nat chain w/o ncard & eq 540; ncard piece 290; final rw eq 80.

## Failed (run 6)
- `is_fiber_iff_generates_quotient_point _ _ _ _ _ x y`: +200hb (worse).
- dot forms `h.mul_left`, `h.lt_succ`, `h.le_of_lt_succ` on Nat.le: don't exist.
- No Mathlib lemma `s.card ≤ t.ncard` from `↑s ⊆ t` (exact? fails).
- ℕ∞ `2*a ≤ 2*b`: nonneg_left+bot_le (425, baseline 325) is cheapest; mul_le_mul' 940, mul_right_mono 729, add_le_add n/a.

## Older failed
- term-mode `let ⟨g', _, h⟩ := ...`: +1300 hb. `rw [fiberwiseClose, ...] at`: +185hb. `h ▸`: fails.
- dropping the BBF_Code binder ascription entirely: g' type unknown.
- `Finset.coe_image ▸`, `Set.ncard_coe_finset _ ▸`: fail. omega anywhere (~300-500hb).
- `zero_le` signature differs across versions -> use bot_le.

## Next ideas
- Look for other spots where explicit args force coercions (big win pattern!).
- Nat chain 540hb: dig with sorry-substitution (is_fiber part, card_fin, mul_left_comm, coe_lt_coe.1 h_fw delta).
- Final eq rw alternatives (Nat.sub_sub / Nat.add_sub_cancel') probably not shorter.
- Bash: sed -i / redirects / heredoc python need approval; use Write tool. grep outside workspace blocked.
- GPT Astra line notes (tail):
...ged on v4.31.0, v4.30.0, v4.29.0, and v4.28.0. Statement checked byte-for-byte against original.lean. Starting point: 288 tokens / 3004 heartbeats / score 87.18.

Successful incremental changes:
- Replace `Set.mem_univ _` in the nonempty witness with `trivial`: 287 / 3004.
- Inline the Hamming bound into the concluding inequality with `refine`, using `((ENat.coe_le_coe (m := sInf S * 2 ^ steps)).mpr ?_)`: 288 / 2963.
- Move `classical` and `rw [← hg, Set.ncard_eq_toFinset_card']` before the cardinality proof. Remove Y_bad and use `Finset.biUnion _`, letting the RHS of `Finset.card_biUnion_le_card_mul _ _ _ ?_` determine the bad-fiber finset: 279 / 2543.
- Pass the biUnion fiber function positionally instead of `(t := ...)`: 277 / 2543.

Tested alternatives:
- [tested: remove `dsimp only at hg` -> harness repairs ncard rw to simp_rw; 283 / 3145, worse]. Retain dsimp.
- [tested: replace fin_ℓ_lt_ℓ_add_one with i.isLt.trans_le (Nat.le_succ _) -> 290 / 3074, worse].
- [tested: remove Nat.lt_succ_of_le, use trans_lt and Nat.lt_succ_self in final simp -> fails unless BBF_CodeDistance is also unfolded; with it, 288 / 2966, slightly worse].
- ENat.coe_le_coe uses implicit parameters `n` and `m`; named arguments must be applied to the iff theorem before `.mpr`, not to Iff.mpr.

Possible next small experiment: use `Nat.sub_add_eq` instead of `← Nat.sub_sub` in the final simp. Not tested.

