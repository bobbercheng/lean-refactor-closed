/- T3 closer table, phase A (harness/tools/tables/gen_closers.py prepends the environment's import line and runs this file).
Rule: every leading token of the `tactic` syntax category of this environment (Std.TreeMap of first tokens; complete, nothing filtered
here) is parsed alone with Lean's own category parser. A token that parses alone is a tactic usable without arguments; the line printed
for it carries the syntax kind. The generator filters these tokens (identifier-shaped, no `?` suggestion form, not forbidden by the
scorer, not a Lean server test fixture) and measures each one on the synthetic goal templates (phase B). -/
open Lean Parser in
#eval show CoreM Unit from do
  let env ← getEnv
  let some cat := (parserExtension.getState env).categories.find? `tactic | throwError "no tactic category"
  for (k, _) in cat.tables.leadingTable.toList do
    let s := match k with | .str _ s => s | _ => k.toString
    match runParserCategory env `tactic s with
    | .ok stx => IO.println s!"T3TOK\t{s}\t{stx.getKind}"
    | .error _ => IO.println s!"T3NOPARSE\t{s}"
