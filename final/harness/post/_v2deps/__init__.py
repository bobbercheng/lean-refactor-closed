"""Vendored dependencies of the post-step (infra/closed_package/post_step.py; README.md section 10), added 2026-11-04 (v2; v4su: the
second module).

The post-step's files (harness/open_post.py, harness/post/*.py) are those of our development commit
93959dcbeea06c46d6297151b318673b06256980 (branch open-post-v4su), byte for byte (v2: ee48034b032380966de26e733f6f6b74fdd503b4), and our
passes of the step on closed run 3's output ran them in checkouts of 715cd39d (post-step v4, the same files without hb_smartunfold) and
6b28b8e1 (the hb_smartunfold pass). Every package definition they reach is the same in this package as at that commit (syntax trees,
docstrings removed), except where CODE_VERSION.md lists it (the check and its result are there), and except two modules this package
does not have:

  probe.open_rederive.opentables   <- probe/open_rederive/opentables.py here, byte-identical to ee48034b's file (sha256 below).
      harness/post/jointres.py `_entry_ok` imports `entry_of` from it (inside a try: without the module, the table-driven sweep ops
      combdrop and ctorshort would propose nothing, unlike in our measurement). `entry_of` reads only the candidate's note and the
      module's constant _CTOR_SHORT; nothing else of the module runs (its other functions read tables relative to its own path and
      are not called by the step).
  harness.funind                   <- harness/funind.py here (v4su), byte-identical to the file at ee48034b, 715cd39d, 93959dcb and
      6b28b8e1 (one sha256, below). harness/post/argon_funind.py imports it at module level (`from harness import funind as FI`; without
      it the op argon_funind could not load). Its own imports are scorer.forbidden and scorer.tokenize (this package's, the same
      definitions). Its module level puts its parent's parent directory on sys.path (in a checkout: the tree's root, already there);
      install() restores sys.path afterwards, so the process's import path is the one our passes had.

install() registers the vendored file under its original module name (sys.modules), so the byte-identical post files import it
unchanged. It is called only by infra/closed_package/post_step.py, in the post-step's own process, before harness.open_post is
imported; nothing of the run (infra/closed_package/run_final.py and what it starts) imports this package or that name. install()
refuses a vendored file whose sha256 is not the recorded one, and never replaces a module of that name that is already loaded from
elsewhere."""
from __future__ import annotations

import hashlib, importlib.util, sys, types
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_COMMIT = "ee48034b"
# module name -> (file under this directory, sha256 of the file at SOURCE_COMMIT)
VENDORED = {
    "probe.open_rederive.opentables": ("probe/open_rederive/opentables.py",
                                       "4576e703718305fadc0cf947ba3548da2e5811e8e853eb996d140b0cb5f32d26"),
    "harness.funind": ("harness/funind.py", "c74eba0c7266aca561b66e7a32e2fcf106abcad906d885d0456087e14f2aef56"),
}


def install() -> dict:
    """Register every VENDORED module under its name; returns {name: file}. Idempotent."""
    import probe  # this package's own namespace package (probe/verify_candidates.py)
    done = {}
    for name, (rel, sha) in VENDORED.items():
        path = HERE / rel
        got = sys.modules.get(name)
        if got is not None:
            if Path(getattr(got, "__file__", "") or "").resolve() != path:
                raise RuntimeError(f"{name} is already loaded from {getattr(got, '__file__', None)}, not the vendored {path}")
            done[name] = str(path)
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != sha:
            raise RuntimeError(f"vendored {path}: sha256 {digest[:16]} is not the recorded {sha[:16]} ({SOURCE_COMMIT})")
        parent, _, leaf = name.rpartition(".")
        if parent not in sys.modules:   # probe.open_rederive: a package holding only the vendored module(s)
            pkg = types.ModuleType(parent)
            pkg.__path__ = []
            pkg.__package__ = parent
            sys.modules[parent] = pkg
            setattr(probe, parent.rpartition(".")[2], pkg)
        spec = importlib.util.spec_from_file_location(name, path)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        saved_path = list(sys.path)   # harness.funind's module level inserts its own parent's parent; the package root is already there
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        finally:
            sys.path[:] = saved_path
        setattr(sys.modules[parent], leaf, mod)
        done[name] = str(path)
    return done
