# putnam_1964_b2
BEST candidate banked: 34 proof tokens, 1159 heartbeats, score 99.07, compatible v4.26.0/v4.25.0. Final candidate is direct target rewrite rather than intermediary cardinality fact.
Plan: classical; `simp_all only [ne_eq, ← Set.disjoint_iff_inter_eq_empty]`; `rw [← Nat.mul_left_inj two_ne_zero, Nat.mul_comm P.card, Nat.two_pow_pred_mul_two Fintype.card_pos, ← Fintype.card_set, ← Set.Intersecting.is_max_iff_card_eq hPP]`; `unfold Set.Intersecting; intros; ext; grind`.
The rw chain multiplies equality by two, commutes only P.card*2, rewrites power, identifies Set S cardinality and applies maximal intersecting family characterization backwards. hPP automatically infers s=P (no named arguments needed).
Library: Set.Intersecting.is_max_iff_card_eq (hs : (↑s).Intersecting) : (∀ t : Finset α, (↑t).Intersecting → s ⊆ t → s = t) ↔ 2*s.card = Fintype.card α. Intersecting is ∀ a∈s,∀ b∈s, ¬Disjoint a b, including equal pairs.
Important: ne_eq needed before reverse Set.disjoint_iff_inter_eq_empty; otherwise simp makes no progress. simp_all only saves 3 tokens over simp ... at hPP hPS. Broad simp_all compiles but costs ~5000 hb, losing score.
Previous architecture have hc := (Set.Intersecting.is_max_iff_card_eq hPP).mp ...; rewrite hc; omega achieved 37 tokens1495hb98.93. New direct rw target was better.
Failed: aesop cannot prove reverse inclusion even after explicit antisymm; grind only [Set.Intersecting] needs Finset.mem_coe,Finset.subset_iff; Finset.ext_iff invalid grind hint even backwards; ext does not introduce forall so intros required; grind! unknown tactic in toolchains.
Polishing: clear hPP after rw yields36 tokens976hb but harness does not bank as improvement; no measurable score win. grind directly [Set.Intersecting,Finset.Subset.antisymm] yields35 tokens1974hb, worse. Reordering normalization simp arguments unchanged. Nat.mul_right_inj architecture costs39 tokens1187hb, worse.
Profile best: 115hb statement floor, 184 normalization, 201 rw, 651 grind, 4 ext, 3 unfold, 1 classical. Nearly at floor of useful token structure.

## Follow-up run
No improvement over the banked 34-token/1159-hb proof. Tested batches:
- `tauto` and `aesop` fail after ext (subset is not converted automatically).
- `intros; ext; grind [Set.Intersecting]` compiles, 35 tokens/1157 hb: no gain.
- `unfold Set.Intersecting; grind [Finset.Subset.antisymm]` compiles, 35 tokens/1954 hb.
- `grind [Finset.ext]` invalid pattern hint.
- `simp_rw [← Set.disjoint_iff_inter_eq_empty] at *` fails (needs ne_eq). Adding ne_eq compiles 35 tokens/1180 hb.
- dsimp instead of unfold compiles but 36 tokens/1171 hb.
- grind only [Finset.mem_coe, Finset.subset_iff] compiles 40 tokens/1169 hb; removing either hint fails. Bare grind only fails.
- grind -lia, -ext, -lookahead each compiles but adds 2 tokens and slightly increases heartbeats.
Keep existing candidate.lean.

## Additional run (current banked 33-token proof)
Current best retained: 33 tokens, 975 hb, score 99.13. Uses mul_pow_sub_one and Nat.mul_right_inj; clear hPP before unfold/intros/ext/grind.
Fresh maximality rewrite explicit antisymm + by_contra + hPS witness compiled at 55 tokens/683hb: less automation but token loss exceeds heartbeat benefit.
Checked variants: ext1 identical 33/975; no unfold + grind [Set.Intersecting] 34/958; grind -mbtc 35/1022; simp only [...] at * instead of simp_all only 35/875 (100hb savings insufficient for two tokens); apply Finset.Subset.antisymm then grind 39/982. None improved score. Candidate unchanged.

### Further wins in this run
Banked NEW BEST score99.21: 29 tokens/958hb. Proof:
```
  simp_all only [Ne, ← Set.disjoint_iff_inter_eq_empty]
  apply Nat.mul_left_cancel Nat.two_pos
  rw [mul_pow_sub_one Fintype.card_ne_zero, ← Fintype.card_set, ← Set.Intersecting.is_max_iff_card_eq hPP]
  clear hPP
  unfold Set.Intersecting
  grind
```
IMPORTANT discoveries: `classical` is unnecessary for this library proof! `apply Nat.mul_left_cancel Nat.two_pos` saves a token over reverse injectivity rewrite and avoids polymorphic two_pos inference overhead (generic two_pos caused ~155 extra hb). `intros; ext` are BOTH unnecessary: grind automatically introduces and applies Finset ext. `Ne` instead of ne_eq saves 4hb at same tokens. Removing clear hPP yields27tokens/1141hb, slightly worse score; removing unfold fails because grind does not unfold Intersecting automatically. Folding unfolding into simp_rw chain =29/1101; replacing unfold with grind [Set.Intersecting] =28/1160 if no clear. Pure automation via have hc := is_max_iff_card_eq hPP; clear hPP; grind [Set.Intersecting,Fintype.card_set,mul_pow_sub_one,Fintype.card_ne_zero] compiles26tokens/4921hb, worse.
Grind hints accept names, NOT parenthesized arbitrary expressions on these toolchains; introduce a local fact to pass instantiated theorem (locals automatically used). `have := mul_pow_sub_one Fintype.card_ne_zero (2:ℕ)` needs explicit α:=S on card_ne_zero when no expected type; otherwise instance search stuck.

## Latest follow-up (no improvement)
Retained banked 29-token/958-hb proof (score99.21). Fresh checks:
- No-clear `grind -lia`:29 tokens/1187hb; worse.
- `simp only [Set.Intersecting, Finset.mem_coe] at *` after clear:36/2011; worse.
- `clear hPP; grind [Set.Intersecting]`:30/974; worse.
- `apply mul_left_cancel₀ two_ne_zero` instead of Nat.mul_left_cancel Nat.two_pos:29/1034; worse.
- `grind [-hPP]` and `grind [Set.Intersecting,-hPP]` FAIL: local hypotheses cannot be excluded via this syntax (Unknown constant hPP).
- Folding Set.Intersecting into the target `rw` or `erw` list FAILS: Failed to rewrite using equation theorems for Intersecting. Explicit `unfold` remains necessary (or grind hint, which costs more).
- Already-checked identical variants do not count as fresh checks; harness reports skipped compilation.
No candidate improvement, original banked candidate unchanged.

### Late breakthrough: negated iff projections
NEW BANKED BEST:25tokens/1055hb, score99.26, compatible both toolchains. Replace normalization by `simp_all only [Set.disjoint_iff_inter_eq_empty.not.symm]`. This DIRECTLY matches Ne without separately unfolding it:27tokens/1044hb with `← ...not`; `.not.symm` removes another arrow token (26/1053). Likewise `Fintype.card_set.symm` saves a token over `← Fintype.card_set` (25/1055). Current proof otherwise identical to previous29token winner.
`Set.disjoint_iff_inter_eq_empty.symm.not` gives25/1054, same rounded score (not banked).
Other results: no clear after new normalization+card_symm =23/1238, narrowly worse. `simp only [...] at *` instead of simp_all only =27/919, also narrowly worse.
Field notation `hPP.is_max_iff_card_eq(.symm)` FAILS: hPP is a Function type, not syntactically Set.Intersecting, so Lean searches Function.is_max_iff_card_eq.
New exists_card_eq architecture with explicit Q, P=Q and cancel compiles50/1010, worse. Compressed existence fact + grind FAILS (even unfolding Intersecting): grind cannot derive equality of finsets just from negated cardinality equality without a membership witness. Intermediary maximality fact architecture compiles36/964, worse.
Grind no-clear flag variants -inj/-order/-ring/-funext/-lookahead/-abstractProof all compile29/1174-1188 using old normalization, none improve. `with_reducible grind` does not unfold Intersecting. `Nat.eq_of_mul_eq_mul_left Nat.two_pos` same cost as Nat.mul_left_cancel Nat.two_pos.

## Current follow-up run (no new best)
Retained 25-token/1055-hb score99.26 candidate unchanged. Fresh goal inspection confirms final target after rw is maximality; clear hPP prevents irrelevant intersecting pair instantiations.
[tested: no-clear grind -mbtc ->25tokens1285hb; no-clear grind -ac ->25tokens1282hb; clear grind -mbtc ->27tokens1101hb; clear grind -ac ->27tokens1099hb]. `grind -splits` invalid: splits is not boolean-valued.
Fresh automation architecture: normalized hPP + `have := Set.Intersecting.is_max_iff_card_eq hPP; clear hPP; grind only [Set.Intersecting,Fintype.card_set,mul_pow_sub_one,Fintype.card_ne_zero,Finset.mem_coe,Finset.subset_iff]` compiles27tokens4467hb. No-clear broad grind architecture20tokens5205hb; target multiplied first + only grind30tokens4634hb. Finset.ext_iff remains invalid grind pattern hint.
[tested: clear_except hPS -> unknown tactic; replace hPP with is_max iff then rw backwards ->27tokens5032hb; simp_rw instead of rw ->25tokens1203hb]. None scored better. Prior notes saying no further progress possible are not proven; these are only measured negatives.

## Follow-up r9 (no new best)
Retained current candidate: 25 tokens, 1055 hb, score 99.26. Profile: statement floor115, simp_all272, multiplication cancellation4, rw163, clear0, unfold3, grind498.
[tested: replacing `clear hPP; unfold Set.Intersecting; grind` with `grind [Set.Intersecting]` -> compiles24tokens1256hb, not banked. With `clear hPP; grind [Set.Intersecting]`:26tokens1071hb. `grind [= Set.Intersecting]`:25tokens1256hb.]
[tested: `grind -ext` after clear/unfold -> fails (needs finset extensionality); `grind only [Finset.mem_coe, Finset.subset_iff]` after clear/unfold -> compiles31tokens1124hb.]
[tested: `grind -lookahead [Set.Intersecting]` without clear/unfold ->26tokens1303hb; `grind only [Set.Intersecting]` fails (does not convert coe membership/subset); adding Finset.Subset.antisymm to bare hint ->26tokens2026hb.]
Simp_rw normalization and simp-only-at-* alternatives were already checked in earlier runs; harness skipped duplicate attempts. `Set.disjoint_iff` concludes subset-of-empty, not equality. `Set.not_disjoint_iff` concludes exists common element; no `Set.intersecting_iff` constant exists. No change to best proof.
