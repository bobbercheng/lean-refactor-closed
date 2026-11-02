/- Simp / grind configuration table query (harness/tools/tables/gen_simp_config.py runs it on every installed core toolchain and writes
simp_config_fields.json). Rule: the configuration structure each tactic elaborates its options into (Lean.Elab.Tactic.elabSimpConfig:
simp and simpa use SimpKind.simp -> Lean.Meta.Simp.Config, simp_all uses SimpKind.simpAll -> Lean.Meta.Simp.ConfigCtx; grind without
`=>` uses Lean.Elab.Tactic.elabGrindConfig -> Lean.Grind.Config) is enumerated completely: every field of the flattened structure
(parents' fields first, Lean's declaration order, nothing filtered by name) with its type and, for Bool and Nat fields, its default
(the field of the structure instance `{}`, reduced by whnf). Then each tactic runs, with the state restored after each run
and under a heartbeat limit: bare, and for every Bool field toggled away from its default in both spellings, the option form `+f` / `-f`
and the config form `(config := { f := v })` (no field is probed by name: the 2026-10-22 review removed a discharge-depth grid that
named one field by hand). Each form runs on the goal True (accepted: no exception and no logged error) and on the goal False (closed: accepted and no goal left; a
setting under which the tactic closes False closes goals without a proof, e.g. by `sorry`). Printed: F <structure> <index> <field>
<type> <default>, T <tactic> <structure>, B <tactic> <accepted on True> <closes False>, P <tactic> <form opt|cfg> <field>
<setting> <accepted on True> <closes False>. -/
import Lean
open Lean Elab Meta Term Tactic Command

/-- Running `stx` on a fresh goal `goal` (state and message log restored): (no exception and no logged error, and no goal left). -/
def runOn (goal : Name) (stx : Syntax) : TermElabM (Bool × Bool) := do
  let s ← saveState
  let msgs ← Core.getMessageLog
  modifyThe Core.State fun st => { st with messages := {} }
  let mv ← mkFreshExprMVar (mkConst goal)
  let r ← tryCatchRuntimeEx
    (do
      let gs ← withCurrHeartbeats <| withTheReader Core.Context (fun c => { c with maxHeartbeats := 20000 * 1000 }) <|
        Term.withoutErrToSorry <| Tactic.run mv.mvarId! (evalTactic stx)
      pure (true, gs.isEmpty))
    (fun _ => pure (false, false))
  let errs := (← Core.getMessageLog).hasErrors
  s.restore
  modifyThe Core.State fun st => { st with messages := msgs }
  pure (r.1 && !errs, r.1 && !errs && r.2)

/-- (accepted on the goal True, closes the goal False). -/
def probe (stx : Syntax) : TermElabM (Bool × Bool) := do
  pure ((← runOn ``True stx).1, (← runOn ``False stx).2)

def tacticForm (tac opt : String) : String :=
  if tac == "simpa" then s!"simpa {opt} using True.intro" else s!"{tac} {opt}"

#eval show CommandElabM Unit from do
  let env ← getEnv
  let structs : List String := ["Lean.Meta.Simp.Config", "Lean.Meta.Simp.ConfigCtx", "Lean.Grind.Config"]
  let tactics : List (String × String) :=
    [("simp", "Lean.Meta.Simp.Config"), ("simpa", "Lean.Meta.Simp.Config"), ("simp_all", "Lean.Meta.Simp.ConfigCtx"),
     ("grind", "Lean.Grind.Config")]
  liftTermElabM do
    -- (field, type, default) of every structure, in declaration order
    let mut fields : Std.HashMap String (Array (String × String × String)) := {}
    for sn in structs do
      let n := sn.toName
      unless isStructure env n do throwError s!"{sn} is not a structure"
      let fs := getStructureFieldsFlattened env n (includeSubobjectFields := false)
      let mut acc := #[]
      for i in [0:fs.size] do
        let f := fs[i]!.toString
        let some stx := (Parser.runParserCategory env `term s!"(\{} : {sn}).{f}").toOption
          | throwError s!"{sn}.{f} does not parse"
        let e ← instantiateMVars (← Term.elabTerm stx none)
        Term.synthesizeSyntheticMVarsNoPostponing
        let e ← instantiateMVars e
        let ty ← whnf (← inferType e)
        let tyName := if ty.isConst then ty.constName!.toString else "other"
        let v ← withTransparency .all (whnf e)
        let dflt ← if tyName == "Bool" then
            pure (if v.isConstOf ``Bool.true then "true" else if v.isConstOf ``Bool.false then "false" else "?")
          else if tyName == "Nat" then
            pure (match (← (Meta.evalNat v).run) with | some k => toString k | none => "?")
          else pure "-"
        IO.println s!"F\t{sn}\t{i}\t{f}\t{tyName}\t{dflt}"
        acc := acc.push (f, tyName, dflt)
      fields := fields.insert sn acc
    for (tac, sn) in tactics do
      IO.println s!"T\t{tac}\t{sn}"
      let some bare := (Parser.runParserCategory env `tactic (tacticForm tac "")).toOption
        | throwError s!"bare {tac} does not parse"
      let (bt, bf) ← probe bare
      IO.println s!"B\t{tac}\t{bt}\t{bf}"
      for (f, tyName, dflt) in fields.getD sn #[] do
        let mut forms : Array (String × String) := #[]
        if tyName == "Bool" && (dflt == "true" || dflt == "false") then
          let flip := if dflt == "true" then "false" else "true"
          forms := forms.push ("opt", (if dflt == "true" then "-" else "+") ++ f)
          forms := forms.push ("cfg", s!"(config := \{ {f} := {flip} })")
        for (form, setting) in forms do
          let (ok, closesFalse) ← match (Parser.runParserCategory env `tactic (tacticForm tac setting)).toOption with
            | some stx => probe stx
            | none => pure (false, false)
          IO.println s!"P\t{tac}\t{form}\t{f}\t{setting}\t{ok}\t{closesFalse}"
