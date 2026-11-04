KNOWLEDGE BRIEF (facts and skills only — NO proofs are given; discover them yourself and go further)
CROSS-LINE DIGEST for putnam_1964_b2
- Union best (a landmark reached by another line — your proofs are your own): 98.57 from the bounty compile () (bounty), 45 tokens, 2337 heartbeats.
- Each line's best: Opus 5.5 line 97.3, GPT Astra line 97.87, Flash line 95.83.
- Exchange rate on this problem: 1 token = 0.019 points, 100 heartbeats = 0.025 points.
- Lexer rules (scorer/tokenize.py): `f $ g x` is one token less than `f (g x)` (`<|` saves nothing); `λx =>` one less than `fun x =>`; a dotted projection chain like `h.2.1` is one token. A normalizer applies these afterwards anyway, so spend checks on structure.
- Opus 5.5 line notes (tail):
# Notes putnam_1964_b2
- BEST: score 97.30 (127 tokens, ~1160 hb, both toolchains). candidate.lean holds it.
  Structure: classical; have := Finset.card_compl P; rw [show Pᶜ = P.image compl from Finset.ext fun A => by
  rw [mem_compl, mem_image]; exact ⟨fwd, bwd⟩, card_image_of_injective _ compl_injective, Fintype.card_set,
  ← Nat.two_pow_pred_mul_two Fintype.card_pos] at this; omega.
- Run-4 wins (146 -> 127): no push_neg; use hPS as a term via nested anonymous constructors
  (by_contra fun hc => hPS ⟨A, hA, fun U hU hAU => hPS ⟨_, hc, fun V hV hAV => ...⟩⟩);
  inline `have h` as `show .. from` inside rw; `B.inter_compl_self` (dot notation, 1 token);
  `fun x h` + h.1/h.2 instead of ⟨hu,hv⟩ pattern; NO case split: x ∈ Aᶜ is defeq to x ∈ A → False, so
  `hAV.subset ⟨(hAU.subset ⟨·, h.1⟩), h.2⟩`.
- Failed: `A.compl_compl` (A : Set = function type, resolves to Function.*); `fun ⟨B, hB, rfl⟩` (rfl not substituted
  in that fun-pattern); dropping Finset.mem_compl from rw (not defeq); `<|` instead of parens: no token gain;
  `<| e ▸ ...` before `⟩,` broke the parser.
- `classical` is required (DecidableEq (Set S), HasCompl (Finset _)).
- Harness gotcha: the sandbox blocks grep on Mathlib and sed -i/python heredoc; use the Write tool to rewrite files.
- Remaining ideas: probably at the floor; maybe a lemma for U∩V=∅ from A∩U=∅ and Aᶜ∩V=∅.
- GPT Astra line notes (tail):
...he empty set here).
- Generic `disjoint_iff` requires `erw` and costs more than the set-specific lemma.
- Omitting `two_ne_zero` from `Nat.mul_left_inj` leaves the multiplication equality uncancelled.
- `Nat.add_self_inj` does not exist.
- Combining the final conversions with `simp only [← Set.disjoint_iff_inter_eq_empty, disjoint_compl_left_iff] at hu hv ⊢` compiles but adds heartbeats at the same token count. `simp_rw` saves one token but almost exactly loses the gain in heartbeats. Broad `simp` is worse.
- `simp_all only` with those lemmas simplifies the goal to False, so the existing final disjointness term no longer fits.
- Earlier attempts normalizing hPP and hPS globally to disjointness require `ne_eq` and cost more heartbeats than they save in tokens.

Confirmed lemmas: Set.disjoint_iff_inter_eq_empty, disjoint_compl_left_iff, Finset.card_bijective, compl_bijective, compl_involutive.bijective, Finset.card_add_card_compl, Fintype.card_set, pow_sub_one_mul, Nat.mul_left_inj, two_ne_zero.

All checks need `export PATH=/home/user/.elan/bin:$PATH` before the supplied Python harness.

Next idea: only modest gains seem likely. The counting and maximality arguments are already compact. The library theorem `Set.Intersecting.is_max_iff_card_eq` exists in Combinatorics/SetFamily/Intersecting.lean, but converting maximality to its premise seems unlikely to beat this direct proof.

