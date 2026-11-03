/- Relation table + instance index query (harness/tools/tables/gen_relations.py runs it once per library environment with the library's
root module imported and writes relations.json and instances.json). Everything below is a shape test on the TYPE of every theorem in the
environment (Init, Std, Batteries, Mathlib and the library itself); nothing is keyed on a name. With `∀ xs, concl` the theorem's type
telescoped (xs: binders, hyps: the Prop-typed binders) and `rel e = (R, a, b)` when e is `R .. a b` with a constant head R and two last
arguments:
  S  strengthening R' ⇒ R:   concl = R a b, a b distinct fvars; exactly one hyp, of the form R' a b (dir imp) or R' b a (dir flip), R' ≠ R
     also `R' a b ↔ R a b` with no hyps: two lines, dir iff_mp (R' → R via .mp) and iff_mpr (R → R' via .mpr) with R and R' as written
  C  congruence of R over the constructor c: concl = R (c s₁..sₙ) (c t₁..tₙ) (same head c, same arity), every position either shared
     (sᵢ ≡ tᵢ) or related (sᵢ, tᵢ fvars with a hyp Rᵢ sᵢ tᵢ), at least one related, every hyp used; `same` = every Rᵢ is R
  O  one-sided: concl = R u v with exactly one of u, v an application `c ..` having the other side, or a hyp partner of it, as an argument:
     `R u w → R u (c .. w ..)` (side R), `R w v → R (c .. w ..) v` (side L), or no hyp: `R u (c .. u ..)` / `R (c .. v ..) v`
  F  reflexivity: concl = R a a, a an fvar, no hyps
  L  least / greatest element: concl = R u b (side L) or R a u (side R) with the other side an fvar and u a constant application whose
     arguments are all types, type-class instances or fvars that are types (no data)
  B  binder bridge: concl = P ↔ Q with P and Q both ∀- or both ∃-headed (line: the binder types' heads)
  I  instance index: every constant registered as an instance whose class appears as an instance-implicit binder in a declaration of the
     library's own modules (module root = the imported root): name, class, counts of explicit / instance / implicit binders
Fields are tab-separated; names are printed fully qualified; the module root of the theorem is the last field of S/C/O/F/L/B lines.
Theorems and constructors (the rules of an inductive relation) are scanned; deprecated and internal names are skipped. -/
import LRA_IMPORT_ROOT
open Lean Meta Elab Command

def rootOf (env : Environment) (n : Name) : Name :=
  match env.getModuleIdxFor? n with
  | some i => (env.header.moduleNames[i.toNat]!).getRoot
  | none => .anonymous

/-- `(R, a, b)` when `e` is `R .. a b` with a constant head and at least two arguments. -/
def relOf (e : Expr) : Option (Name × Expr × Expr) :=
  let f := e.getAppFn
  let args := e.getAppArgs
  if f.isConst && args.size ≥ 2 then some (f.constName!, args[args.size - 2]!, args[args.size - 1]!) else none

/-- Quick pre-filter on the un-telescoped type: the body is an application with a constant head and ≥ 2 arguments, or an `Iff`. -/
def quickShape (ty : Expr) : Bool :=
  let b := ty.getForallBody
  let f := b.getAppFn
  f.isConst && (b.getAppNumArgs ≥ 2)

def isTypeLike (x : Expr) : MetaM Bool := do
  let t ← inferType x
  if t.isSort then return true
  let t ← whnfR t
  if t.isSort then return true
  if let some c := t.getAppFn.constName? then
    return isClass (← getEnv) c
  return false

def noData (u : Expr) : MetaM Bool := do
  let f := u.getAppFn
  if !f.isConst then return false
  for x in u.getAppArgs do
    if x.isFVar || x.isApp || x.isConst then
      if !(← isTypeLike x) then return false
  return true

def propHyps (xs : Array Expr) : MetaM (Array Expr) := do
  let mut out := #[]
  for x in xs do
    if ← isProp (← inferType x) then out := out.push x
  return out

def fmtRel (r : Name) : String := r.toString

/-- One theorem: prints its classification lines. -/
def classify (n : Name) (ci : ConstantInfo) (root : Name) : MetaM Unit := do
  unless quickShape ci.type do return
  forallTelescope ci.type fun xs concl => do
    let hyps ← propHyps xs
    let hypRels ← hyps.mapM fun h => do pure (relOf (← whnfR (← inferType h)))
    let concl ← whnfR concl
    let rt := fmtRel root
    -- Iff forms
    if concl.isAppOfArity ``Iff 2 then
      let P := concl.getArg! 0
      let Q := concl.getArg! 1
      if hyps.isEmpty then
        match relOf P, relOf Q with
        | some (r1, a1, b1), some (r2, a2, b2) =>
          if a1.isFVar && b1.isFVar && a1 != b1 && a1 == a2 && b1 == b2 && r1 != r2 then
            IO.println s!"S\t{n}\t{r1}\t{r2}\tiff_mp\t{rt}"
            IO.println s!"S\t{n}\t{r2}\t{r1}\tiff_mpr\t{rt}"
        | _, _ => pure ()
        let bh (e : Expr) : Option (String × Name) :=
          if e.isForall then some ("forall", e.bindingDomain!.getAppFn.constName?.getD .anonymous)
          else if e.isAppOfArity ``Exists 2 then
            some ("exists", (e.getArg! 0).getAppFn.constName?.getD .anonymous)
          else none
        match bh P, bh Q with
        | some (k1, d1), some (k2, d2) =>
          if k1 == k2 then IO.println s!"B\t{n}\t{k1}\t{d1}\t{d2}\t{rt}"
        | _, _ => pure ()
      return
    let some (R, a, b) := relOf concl | return
    -- strengthening
    if a.isFVar && b.isFVar && a != b && hyps.size == 1 then
      if let some (R', a', b') := hypRels[0]! then
        if R' != R then
          if a' == a && b' == b then IO.println s!"S\t{n}\t{R'}\t{R}\timp\t{rt}"
          else if a' == b && b' == a then IO.println s!"S\t{n}\t{R'}\t{R}\tflip\t{rt}"
      return
    -- reflexivity
    if a.isFVar && a == b && hyps.isEmpty then
      IO.println s!"F\t{n}\t{R}\t{rt}"
      return
    -- least / greatest
    if hyps.isEmpty && b.isFVar && !a.isFVar && a.getAppFn.isConst then
      if ← noData a then IO.println s!"L\t{n}\t{R}\t{a.getAppFn.constName!}\tL\t{rt}"
    if hyps.isEmpty && a.isFVar && !b.isFVar && b.getAppFn.isConst then
      if ← noData b then IO.println s!"L\t{n}\t{R}\t{b.getAppFn.constName!}\tR\t{rt}"
    -- congruence
    let fa := a.getAppFn
    let fb := b.getAppFn
    if fa.isConst && fb.isConst && fa.constName! == fb.constName! && a.getAppNumArgs == b.getAppNumArgs && a.getAppNumArgs > 0 && !hyps.isEmpty then
      let sa := a.getAppArgs
      let sb := b.getAppArgs
      let mut used : Array Bool := hyps.map fun _ => false
      let mut pos : Array String := #[]
      let mut ok := true
      let mut same := true
      let mut related := 0
      for i in [:sa.size] do
        if sa[i]! == sb[i]! then pos := pos.push "="
        else if sa[i]!.isFVar && sb[i]!.isFVar then
          let mut found := false
          for j in [:hyps.size] do
            if !found && !used[j]! then
              if let some (Rj, aj, bj) := hypRels[j]! then
                if aj == sa[i]! && bj == sb[i]! then
                  used := used.set! j true; found := true; related := related + 1
                  pos := pos.push (fmtRel Rj)
                  if Rj != R then same := false
          if !found then ok := false
        else ok := false
      if ok && related > 0 && used.all id then
        IO.println s!"C\t{n}\t{R}\t{fa.constName!}\t{sa.size}\t{String.intercalate "," pos.toList}\t{same}\t{rt}"
      return
    -- one-sided
    if hyps.size ≤ 1 then
      let side (u v : Expr) : MetaM (Option String) := do   -- u plain side, v = c .. w ..
        if !v.getAppFn.isConst || v.getAppNumArgs == 0 then return none
        let args := v.getAppArgs
        if hyps.isEmpty then
          if u.isFVar && args.contains u then return some s!"{v.getAppFn.constName!}\t0"
          return none
        match hypRels[0]! with
        | some (R', x, w) =>
          if R' == R && x == u && w.isFVar && args.contains w then return some s!"{v.getAppFn.constName!}\t1"
          return none
        | none => return none
      if a.isFVar || hyps.size == 1 then
        if let some s ← side a b then IO.println s!"O\t{n}\t{R}\t{s}\tR\t{rt}"
      let sideL (u v : Expr) : MetaM (Option String) := do
        if !u.getAppFn.isConst || u.getAppNumArgs == 0 then return none
        let args := u.getAppArgs
        if hyps.isEmpty then
          if v.isFVar && args.contains v then return some s!"{u.getAppFn.constName!}\t0"
          return none
        match hypRels[0]! with
        | some (R', w, y) =>
          if R' == R && y == v && w.isFVar && args.contains w then return some s!"{u.getAppFn.constName!}\t1"
          return none
        | none => return none
      if let some s ← sideL a b then IO.println s!"O\t{n}\t{R}\t{s}\tL\t{rt}"

/-- (explicit, instance-implicit, implicit binders, carrier): the carrier is `var` when the class's last argument is a bound variable (an
instance over any type), else the head constant of that argument (an instance for one type former). -/
def binderCounts (ty : Expr) : MetaM (Nat × Nat × Nat × String × String) := do
  forallTelescope ty fun xs concl => do
    let mut e := 0; let mut i := 0; let mut m := 0
    let mut needs : Array String := #[]
    for x in xs do
      let d ← x.fvarId!.getDecl
      match d.binderInfo with
      | .default => e := e + 1
      | .instImplicit =>
        i := i + 1
        needs := needs.push ((← whnfR d.type).getAppFn.constName?.getD .anonymous).toString
      | _ => m := m + 1
    let args := concl.getAppArgs
    let carrier := if args.size == 0 then "none" else
      let last := args[args.size - 1]!
      if last.isFVar then "var" else match last.getAppFn.constName? with
        | some c => c.toString
        | none => "other"
    return (e, i, m, carrier, String.intercalate "," needs.toList)

/-- Classes appearing as instance-implicit binders in the declarations of modules under `root`. -/
def libClasses (env : Environment) (root : Name) : MetaM (Std.HashSet Name) := do
  let mut out : Std.HashSet Name := {}
  for (n, ci) in env.constants.toList do
    if n.isInternal || rootOf env n != root then continue
    let found ← try
      forallTelescope ci.type fun xs _ => do
        let mut acc : Array Name := #[]
        for x in xs do
          let d ← x.fvarId!.getDecl
          if d.binderInfo == .instImplicit then
            if let some c := (← whnfR d.type).getAppFn.constName? then acc := acc.push c
        return acc
      catch _ => pure #[]
    for c in found do out := out.insert c
  return out

#eval show CommandElabM Unit from do
  let env ← getEnv
  let root := `LRA_IMPORT_ROOT
  IO.println s!"M\t{root}"
  liftTermElabM do
    let mut nThm := 0
    for (n, ci) in env.constants.toList do
      if n.isInternal || Linter.isDeprecated env n then continue
      unless (ci matches .thmInfo _) || (ci matches .ctorInfo _) do continue
      nThm := nThm + 1
      try
        withCurrHeartbeats <| withTheReader Core.Context (fun c => { c with maxHeartbeats := 2000 * 1000 }) <|
          classify n ci (rootOf env n)
      catch _ => pure ()
    IO.println s!"N\t{nThm}"
    let classes ← libClasses env root
    IO.println s!"K\t{classes.size}"
    for (n, ci) in env.constants.toList do
      if n.isInternal then continue
      unless ← isInstance n do continue
      let cls := ci.type.getForallBody.getAppFn.constName?.getD .anonymous
      try
        let (e, i, m, carrier, needs) ← binderCounts ci.type
        -- the library's binder classes, plus every instance over any type with at most one needed class (the parent projections and
        -- one-step derivations that close the class hierarchy for the pin family)
        if classes.contains cls || (carrier == "var" && e == 0 && i ≤ 1) then
          IO.println s!"I\t{n}\t{cls}\t{e}\t{i}\t{m}\t{carrier}\t{needs}\t{rootOf env n}"
      catch _ => pure ()
