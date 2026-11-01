/- T1 projection table query (harness/tools/tables/gen_projections.py writes the table from this output).
Rule: every structure declared in a module under `Init` or `Mathlib` in the environment below, with its direct fields in declaration order
(Lean.getStructureFields: subobject fields `toParent` included, which is how `x.i` numbers them), the parent of each subobject field, and
whether the structure is a class or lives in Prop; then, for every field name, how many declarations of the same module slice end with
that name as a projection function and as anything else. Nothing is filtered by name. -/
import Mathlib.Logic.Equiv.Defs
import Mathlib.Order.Hom.Basic
import Mathlib.Algebra.Group.Hom.Defs
import Mathlib.Data.Finset.Defs

open Lean Meta Elab Command

def inSlice (env : Environment) (n : Name) : Bool :=
  match env.getModuleIdxFor? n with
  | some i =>
    let m := env.header.moduleNames[i.toNat]!
    m.getRoot == `Init || m.getRoot == `Mathlib
  | none => false

partial def resultSort : Expr → Expr
  | .forallE _ _ b _ => resultSort b
  | e => e

#eval show CommandElabM Unit from do
  let env ← getEnv
  let mut structs : Array Name := #[]
  for (n, _) in env.constants.toList do
    if isStructure env n && inSlice env n && !n.isInternal then
      structs := structs.push n
  structs := structs.qsort (fun a b => a.toString < b.toString)
  let mut fieldNames : Std.HashSet String := {}
  for s in structs do
    let some ci := env.find? s | continue
    let fs := getStructureFields env s
    let mut parts : Array String := #[]
    for f in fs do
      fieldNames := fieldNames.insert f.toString
      match isSubobjectField? env s f with
      | some p => parts := parts.push s!"{f}:{p}"
      | none => parts := parts.push f.toString
    let prop := resultSort ci.type == .sort .zero
    IO.println s!"S\t{s}\t{isClass env s}\t{prop}\t{",".intercalate parts.toList}"
  let mut proj : Std.HashMap String Nat := {}
  let mut other : Std.HashMap String Nat := {}
  for (n, _) in env.constants.toList do
    if !inSlice env n || n.isInternal then continue
    match n with
    | .str _ last =>
      if fieldNames.contains last then
        if (env.getProjectionFnInfo? n).isSome then
          proj := proj.insert last (proj.getD last 0 + 1)
        else
          other := other.insert last (other.getD last 0 + 1)
    | _ => pure ()
  let names := fieldNames.toArray.qsort (· < ·)
  for f in names do
    IO.println s!"N\t{f}\t{proj.getD f 0}\t{other.getD f 0}"
