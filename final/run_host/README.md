# Run-host scripts (not package code)

The scripts we ran on our own hosts around the package's one command for the closed official runs. The package does not need them:
`infra/closed_package/run_final.py` (README sections 2 and 3) is the whole pipeline, and none of the files here is imported or read by
it. They are here so the steps of README section 9 can be checked against what ran. Copies are what ran, apart from comment edits for
publication: the public-release scrub (the same tool as the code; [`../CODE_VERSION.md`](../CODE_VERSION.md)) and, by hand, a few
attributions of decisions and our development host's name.

| file | what | used by |
|---|---|---|
| `azure_vm/vm_setup.sh` | one-time base setup of an Azure CPU VM (Ubuntu 24.04 x86-64, D64ads_v7): packages, Docker, Miniconda (Python 3.13) with the harness's Python packages, user lingering for systemd user units; no credentials | both run hosts |
| `azure_vm/nvme_scratch.sh` | RAID0 + ext4 over the VM's local NVMe disks, mounted at `/scratch` (the runs' `--scratch-root`); the disks are wiped on every deallocate | both run hosts |
| `closed_run2/final2.sh` | closed run 2's launcher: `plan`, `checkenvs` / `fixenvs` (each environment the rows use must be a real directory in the checkout's `envs/`, README section 9), `run` / `launch` (the exact `run_final.py run` command with `--bets D2,D3,D4,D4P,D4S`, as a systemd user unit), `status`, `stop` | run 2 |
| `closed_run2/final2_envs.py` | lists the environment directories every pin of every row compiles in (for `checkenvs` / `fixenvs`) | runs 2 and 3 |
| `closed_run3/final3.sh` | closed run 3's launcher: `final2.sh` with run 3's paths and tag, `--bets D2,D3,D4,D4P,D4S,D4C,D4N`, and a 48 GB memory cap on the launcher unit (README section 9) | run 3 |
| `closed_run3/xfer.sh` | copies run 2's environment directories (with the env fix's edits), `~/.elan`, the session image and run 2's rows and reference heartbeats from run 2's host to run 3's (destination and key as variables here) | run 3 |
| `closed_run3/refcheck.py` | re-measures two reference proofs on run 3's host against run 2's reference file | run 3 |
| `shard_watchdog.py` | restarts a shard that is still down 15 minutes after a crash once `run_final.py run` has used its one restart (`--max-restarts 1`), by the package's own `run_final.launch()` re-running the shard's `run.sh` unchanged (a restart resumes: spend kept, the $3.00 cap holds); at most 4 per shard; runs the package's merge when the launcher has exited; never after `run_final.py stop`. Started 2026-11-02 20:19 UTC on both run hosts | runs 2 and 3 |
