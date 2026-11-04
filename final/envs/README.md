# envs/

`infra/closed_package/install_envs.sh` puts the Lean environments here: one git worktree per (project, pinned toolchain) named
`<source>-<toolchain>` (PutnamBench rows use `mathlib-<toolchain>`), the upstream clones they come from (`mathlib4`, `<repo>.git-main`),
`final_envs.json` (the list derived from the rows) and `logs/`. Everything here except this file is git-ignored.

The sessions' worktrees link these environments from the repository's MAIN working tree. When the package runs as a git worktree
of another checkout, the environments must be in (or linked into) that main checkout's `envs/`, at the rows' pinned commits
(`../README.md`, section 9).

Keep this file tracked: the pipeline reads `git status` of `envs/` to link the environments into the sessions' worktree and to mask
stray files, and a directory with no tracked file at all is reported as one untracked entry, which the sessions' container setup then
mounts twice (`docker: Duplicate mount point`).
