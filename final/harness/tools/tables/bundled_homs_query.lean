/- Bundled-hom specialization table query (harness/tools/tables/gen_bundled_homs.py runs it with `import Mathlib` on each Mathlib pin of
its scope and writes bundled_homs.json). Rule, over the declarations of modules under Init or Mathlib (nothing else is filtered by name):
  structures  every structure that is not a class and whose flattened field list (its own fields and its parents') has a field named
              `map_<x>'` (Mathlib's spelling of a bundled hom's axioms, e.g. the additive or multiplicative one): a bundled hom
  generics    every theorem of the root namespace whose name starts with `map_`, not deprecated
  pairs       for every such structure S and generic g, the theorem S.g when it exists, is not deprecated, and specializes g: with
              the binders of S.g as local hypotheses, Lean's `apply` of g (MVarId.apply: g's arguments as fresh metavariables, its
              conclusion unified with S.g's, its instance arguments synthesized) succeeds on S.g's conclusion under a heartbeat limit
              (the state is restored after each check)
  size        for every such structure, the number of declarations directly in its namespace (internal names excluded)
Printed: R <generics>, S <structure> <size>, P <structure> <generic> <true|false> for every existing non-deprecated S.g. -/
import Mathlib
open Lean Meta Elab Command

def inSlice (env : Environment) (n : Name) : Bool :=
  match env.getModuleIdxFor? n with
  | some i =>
    let m := env.header.moduleNames[i.toNat]!
    m.getRoot == `Init || m.getRoot == `Mathlib
  | none => false

def isMapField (f : Name) : Bool :=
  match f with
  | .str .anonymous s => s.startsWith "map_" && s.endsWith "'"
  | _ => false

def specializes (g s : Name) : MetaM Bool := do
  let st ← saveState
  let r ← tryCatchRuntimeEx
    (withCurrHeartbeats <| withTheReader Core.Context (fun c => { c with maxHeartbeats := 20000 * 1000 }) do
      let ci ← getConstInfo s
      forallTelescope ci.type fun _ concl => do
        let mv ← mkFreshExprMVar concl
        let us ← (← getConstInfo g).levelParams.mapM fun _ => mkFreshLevelMVar
        let _ ← mv.mvarId!.apply (mkConst g us)
        pure true)
    (fun _ => pure false)
  restoreState st
  pure r

#eval show CommandElabM Unit from do
  let env ← getEnv
  let mut roots : Array Name := #[]
  let mut size : Std.HashMap Name Nat := {}
  for (n, ci) in env.constants.toList do
    if n.isInternal || !inSlice env n then continue
    match n with
    | .str .anonymous s =>
      if s.startsWith "map_" && ci matches .thmInfo _ && !Linter.isDeprecated env n then roots := roots.push n
    | .str p _ => size := size.insert p (size.getD p 0 + 1)
    | _ => pure ()
  roots := roots.qsort (fun a b => a.toString < b.toString)
  IO.println s!"R\t{roots.size}"
  let mut structs : Array Name := #[]
  for (n, _) in env.constants.toList do
    if isStructure env n && inSlice env n && !n.isInternal && !isClass env n then
      if (getStructureFieldsFlattened env n (includeSubobjectFields := false)).any isMapField then
        structs := structs.push n
  structs := structs.qsort (fun a b => a.toString < b.toString)
  for s in structs do
    IO.println s!"S\t{s}\t{size.getD s 0}"
  liftTermElabM do
    for s in structs do
      for g in roots do
        let n := s ++ g
        if let some ci := env.find? n then
          if ci matches .thmInfo _ && !Linter.isDeprecated env n then
            IO.println s!"P\t{s}\t{g}\t{← specializes g n}"
