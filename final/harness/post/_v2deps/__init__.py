"""Vendored dependencies of the post-step v2 (infra/closed_package/post_step.py; README.md section 10), added 2026-11-04.

The post-step's files (harness/open_post.py, harness/post/*.py) are those of our development commit
ee48034b032380966de26e733f6f6b74fdd503b4 (branch open-post-v2), byte for byte, and our measurement of the step on closed run 3's output
ran them in a checkout of that commit. Every package definition they reach is the same in this package as at that commit (syntax trees,
docstrings removed; the check and its result are in CODE_VERSION.md), except one module this package does not have:

  probe.open_rederive.opentables   <- probe/open_rederive/opentables.py here, byte-identical to ee48034b's file (sha256 below).
      harness/post/jointres.py `_entry_ok` imports `entry_of` from it (inside a try: without the module, the table-driven sweep ops
      combdrop and ctorshort would propose nothing, unlike in our measurement). `entry_of` reads only the candidate's note and the
      module's constant _CTOR_SHORT; nothing else of the module runs (its other functions read tables relative to its own path and
      are not called by the step).

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
        try:
            spec.loader.exec_module(mod)
        except BaseException:
            sys.modules.pop(name, None)
            raise
        setattr(sys.modules[parent], leaf, mod)
        done[name] = str(path)
    return done
