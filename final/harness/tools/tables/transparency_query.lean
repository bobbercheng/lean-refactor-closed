/- Transparency wrapper table query (harness/tools/tables/gen_transparency.py runs it on every installed core toolchain and writes
transparency_wrappers.json). Rule: every leading token `tok` of this environment's `tactic` syntax category (core Lean: Init + Lean;
complete, nothing filtered by name) is parsed as `tok lra_transparency_probe`, where the probe declared below (the query's own token,
skipped) fails at once with the index of the transparency setting it runs under (Lean.Meta.getTransparency; the index is the
constructor's position in Lean.Meta.TransparencyMode). Each form that parses runs once on the goal `True` under a heartbeat limit, with
the state restored afterwards. A token is a transparency wrapper when its run fails with the probe's report and the reported setting
differs from the bare probe's (the tactic framework's default setting). Printed: N <number of tokens>, B <bare setting>, M <index>
<constructor> for every constructor of Lean.Meta.TransparencyMode in declaration order, L <a> <b> <Lean's TransparencyMode.lt a b,
reduced by whnf> for every pair, W <token> <setting> for every wrapper. -/
import Lean
open Lean Elab Meta Term Tactic Command

syntax (name := lraTransparencyProbe) "lra_transparency_probe" : tactic

@[tactic lraTransparencyProbe] def evalLraTransparencyProbe : Tactic := fun _ => do
  throwError m!"LRA_TRANSPARENCY_PROBE {(← getTransparency).ctorIdx}"

/-- The probe's report in the outcome of running `stx` on a fresh `True` goal (state restored), if any. -/
def probeOutcome (stx : Syntax) : TermElabM (Option Nat) := do
  let s ← saveState
  let msgs ← Core.getMessageLog
  let mv ← mkFreshExprMVar (mkConst ``True)
  let r ← tryCatchRuntimeEx
    (do
      let _ ← withCurrHeartbeats <| withTheReader Core.Context (fun c => { c with maxHeartbeats := 20000 * 1000 }) <|
        Term.withoutErrToSorry <| Tactic.run mv.mvarId! (evalTactic stx)
      pure "")
    (fun e => do pure (← e.toMessageData.toString))
  s.restore
  modifyThe Core.State fun st => { st with messages := msgs }
  match r.splitOn "LRA_TRANSPARENCY_PROBE " with
  | [_, rest] => pure (String.mk (rest.toList.takeWhile Char.isDigit)).toNat?
  | _ => pure none

#eval show CommandElabM Unit from do
  let env ← getEnv
  let some cat := (Parser.parserExtension.getState env).categories.find? `tactic | throwError "no tactic category"
  let mut toks : Array String := #[]
  for (k, _) in cat.tables.leadingTable do
    toks := toks.push k.toString
  toks := toks.qsort (· < ·)
  IO.println s!"N\t{toks.size}"
  let ind ← liftCoreM <| getConstInfoInduct ``Lean.Meta.TransparencyMode
  let ctors := ind.ctors.toArray
  for i in [0:ctors.size] do
    IO.println s!"M\t{i}\t{ctors[i]!}"
  liftTermElabM do
    for a in ctors do
      for b in ctors do
        let some stx := (Parser.runParserCategory env `term s!"Lean.Meta.TransparencyMode.lt {a} {b}").toOption
          | throwError s!"lt {a} {b} does not parse"
        let e ← instantiateMVars (← Term.elabTerm stx (some (mkConst ``Bool)))
        let r ← withTransparency .all (whnf e)
        IO.println s!"L\t{ctors.findIdx? (· == a) |>.getD 0}\t{ctors.findIdx? (· == b) |>.getD 0}\t{r.isConstOf ``Bool.true}"
    let some bare := (Parser.runParserCategory env `tactic "lra_transparency_probe").toOption | throwError "the probe does not parse"
    let some b0 ← probeOutcome bare | throwError "the bare probe did not report"
    IO.println s!"B\t{b0}"
    for tok in toks do
      if tok == "lra_transparency_probe" then continue
      if let some stx := (Parser.runParserCategory env `tactic s!"{tok} lra_transparency_probe").toOption then
        if let some m ← probeOutcome stx then
          if m != b0 then
            IO.println s!"W\t{tok}\t{m}"
