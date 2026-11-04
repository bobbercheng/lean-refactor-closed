from pathlib import Path
s=Path('draft.lean').read_text()
s=s.replace('    sorry', '''    obtain ⟨g, _, he⟩ := Nat.sInf_mem (Set.image_nonempty.mpr
      (Set.univ_nonempty : (Set.univ : Set C).Nonempty))
    exact ⟨g, g.2, he.symm⟩''',1)
o=Path('original.lean').read_text()
b=o[o.index('    -- Let ΔH'):o.index('  -- The minimum distance')]
b=b.replace("g'",'g').replace('    -- Let ΔH be the finset of actually bad x points where f and g disagree.','    rw [hd]')
s=s.replace('    sorry',b.rstrip(),1)
s=s.replace('    sorry', '''    have hf : 2 * d ≤ BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1 :=
      Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt)
    have he : (BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩ - 1) * 2 ^ steps =
        BBF_CodeDistance ℓ 𝓡 ⟨i, by omega⟩ - 1 := by
      dsimp [BBF_CodeDistance]
      rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add]
      congr 2 <;> omega
    have hh := (Nat.mul_le_mul_left 2 hb).trans
      (by simpa only [←mul_assoc] using Nat.mul_le_mul_right (2 ^ steps) hf)
    rw [he] at hh
    exact Nat.lt_of_le_pred (Nat.succ_pos _) hh''',1)
Path('candidate.lean').write_text(s)
