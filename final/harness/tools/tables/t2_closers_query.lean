/- T2 closer table query (harness/tools/tables/gen_t2_closers.py runs this on every installed toolchain and writes t2_closers.json).
Rule: every leading token of the `tactic` syntax category of this environment (core Lean: Init + Lean; nothing is filtered by name) is
parsed bare (`tok`) and with one term argument (`tok x`); each form that parses is run on every goal of the synthetic battery below
(written for this table: generic Prop / Nat goals, no library lemma), bare as is and the argument form with every local hypothesis `h`,
every `h ?_` and `⟨?_, ?_⟩` as the argument, each run under a fresh heartbeat limit and with the state restored afterwards. Each run's
outcome is printed (a token named in the T2_SKIP environment variable is skipped: the generator puts there the tokens whose runs
did not finish in its wall-clock limit on that toolchain): fail (an exception or a logged error), closed (no goal left and no sorry), sorry (closed through sorry), open (goals
left that differ from the input goal), unchanged (it succeeded and left exactly the input goal). The generator turns the counts into a
class per token and form (closer: closes some goal and never leaves one open or unchanged). The five goal-list combinators the T2
scheduler may add are reported as present / absent from the same token table. -/
import Lean
import Std.Data.TreeMap
open Lean Elab Meta Term Tactic Command

/-- (goal, setup tactic): the setup puts the hypotheses in context by name. -/
def battery : List (String × String) := [
  ("∀ (p q : Prop), p → q → p ∧ q", "intro p q hp hq"),
  ("∀ (p q : Prop), (p → q) → p → q", "intro p q h hp"),
  ("∀ (p q : Prop), p ∧ q → q ∧ p", "intro p q h"),
  ("∀ (p q : Prop), p → p ∨ q", "intro p q hp"),
  ("∀ (p : Prop), False → p", "intro p h"),
  ("∀ (n : Nat), n + 0 = n", "intro n"),
  ("∀ (n : Nat), n ≤ n + 1", "intro n"),
  ("2 + 2 = 4", "skip"),
  ("True ∧ True", "skip"),
  ("∀ (p q : Prop), p → q", "intro p q hp"),
  ("∀ (n m : Nat), n = m → m = n", "intro n m h"),
  ("∀ (p q : Prop), p → (p → q) → q", "intro p q hp h"),
  ("∀ (α : Type) (x : α), x = x", "intro α x"),
  ("∀ (p : Prop), p → ¬¬p", "intro p hp"),
  ("∀ (f : Nat → Nat) (n : Nat), f n = f n ∧ n = n", "intro f n"),
  ("∀ (p q r : Prop), (p → q) → (q → r) → p → r", "intro p q r h1 h2 hp"),
  ("∃ n : Nat, n = n", "skip"),
  ("∀ (p : Prop), p → p", "intro p hp"),
  ("∀ (p q : Prop), (True ∧ p) ∨ q", "intro p q"),
  ("∀ (n m : Nat), n + 0 = m", "intro n m"),
  ("∀ (p q : Prop), q → (True ∧ p) ∨ q ∧ q", "intro p q hq")
]

def parseTac (env : Environment) (s : String) : Option Syntax :=
  (Parser.runParserCategory env `tactic s).toOption

/-- Run `tac` on a fresh copy of the battery goal; the outcome word. -/
def runOn (tac : Syntax) (g : MVarId) : TermElabM String := do
  let s ← saveState
  let msgs ← Core.getMessageLog
  let r ← tryCatchRuntimeEx
    (do
      let gs ← withCurrHeartbeats <| withTheReader Core.Context (fun c => { c with maxHeartbeats := 20000 * 1000 }) <|
        Term.withoutErrToSorry <| Tactic.run g (evalTactic tac)
      let err := (← Core.getMessageLog).hasErrors
      if err then pure "fail"
      else if gs.isEmpty then
        let pf ← instantiateMVars (mkMVar g)
        pure (if pf.hasSorry then "sorry" else "closed")
      else if gs == [g] then pure "unchanged"
      else pure "open")
    (fun _ => pure "fail")
  s.restore
  modifyThe Core.State fun st => { st with messages := msgs }
  pure r

/-- The battery goals with their setups run: (index, goal, local hypothesis names). -/
def setupGoals : TermElabM (Array (Nat × MVarId × Array String)) := do
  let env ← getEnv
  let mut out := #[]
  let mut i := 0
  for (gs, su) in battery do
    let some gstx := (Parser.runParserCategory env `term gs).toOption | throwError s!"battery goal {i} does not parse"
    let some sstx := parseTac env su | throwError s!"battery setup {i} does not parse"
    let ty ← Term.elabType gstx
    Term.synthesizeSyntheticMVarsNoPostponing
    let ty ← instantiateMVars ty
    let mv ← mkFreshExprMVar ty
    let rest ← Tactic.run mv.mvarId! (evalTactic sstx)
    match rest with
    | [g] =>
      let names ← g.withContext do
        let lctx ← getLCtx
        pure <| lctx.foldl (fun acc d => if d.isImplementationDetail then acc else acc.push d.userName.toString) #[]
      out := out.push (i, g, names)
    | _ => throwError s!"battery setup {i} left {rest.length} goals"
    i := i + 1
  pure out

#eval show CommandElabM Unit from do
  let env ← getEnv
  let some cat := (Parser.parserExtension.getState env).categories.find? `tactic | throwError "no tactic category"
  let mut toks : Array String := #[]
  for (k, _) in cat.tables.leadingTable do
    toks := toks.push k.toString
  toks := toks.qsort (· < ·)
  IO.println s!"N\t{toks.size}"
  for c in ["rotate_left", "any_goals", "all_goals", "repeat", "repeat'"] do
    IO.println s!"C\t{c}\t{toks.contains c}"
  let skip := ((← IO.getEnv "T2_SKIP").getD "").splitOn ","
  liftTermElabM do
    let goals ← setupGoals
    for tok in toks do
      if skip.contains tok then
        IO.println s!"S\t{tok}"
        continue
      let bare := parseTac env tok
      let arg := parseTac env s!"{tok} x"
      IO.println s!"K\t{tok}\t{bare.isSome}\t{arg.isSome}"
      (← IO.getStdout).flush
      if let some stx := bare then
        for (i, g, _) in goals do
          IO.println s!"R\t{tok}\tbare\t{i}\t{← runOn stx g}"
      if arg.isSome then
        for (i, g, names) in goals do
          let args := names ++ names.map (· ++ " ?_") ++ #["⟨?_, ?_⟩"]
          for a in args do
            if let some stx := parseTac env s!"{tok} {a}" then
              IO.println s!"R\t{tok}\targ\t{i}\t{← runOn stx g}"
