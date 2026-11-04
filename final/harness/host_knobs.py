#!/usr/bin/env python3
"""b66 closed package (retro A5; 2026-10-27): the run's speed and memory knobs derived from the host (nproc, SMT, MemTotal) instead of
literals. The anchor is the Azure VM (Standard_D64ads_v7: 64 vCPU = 32 cores x SMT 2, 256 GB), where every value below was measured or
run (infra/azure/README.md "Recommended settings for 64 vCPU", docs/b65_final.md section 6): one 15-row router = --jobs 15 --compile-slots 32
--workers 15, ROUTER_MEM 160G, memgate claim/reserve 4000/4000, brief 15 row workers x 4 compile workers in a 160g container (it3vm's brief
stalled at 0/15 with the defaults, b63 build log 2026-10-26 20:30); the 60-row final = 4 shards of 15 rows, each --workers 4 --jobs 15
--compile-slots 8, ROUTER_MEM 96G. The formulas reproduce exactly those values at the anchor and scale down to the minimum host
(16 vCPU / 64 GB). Every value can be overridden (run_final.py flags); `why` says how each one was derived.
RAM is the INSTALLED size (review 2026-10-27): /proc/meminfo's MemTotal is 2-5 % below it (kernel and firmware reservations: this
GB10's 128 GB reads 121.7; a 256 GB VM ~250), and at MemTotal the formulas gave the VM 3 sessions per shard (12, not the planned 16),
ROUTER_MEM 94G and 47g containers; installed_gb() rounds MemTotal up to 16 GB (8 GB below 32 GB).

  compile slots (router $0 stages, per shard)  physical cores / shards        the ~32-core knee: 24.9x at 32 compiles, +9 % from 32 to 64
  jobs (rows at once in the $0 stages)         min(rows, 2 x slots)          a row's stages are sequential: more rows than slots keeps them busy
  workers (async ladder sessions, per shard)   min(rows, total / shards),    total = min(16, cores / 2, GB / 16): OpenRouter took 12-16 callers
                                                                             with 0 rate limits; each session also compiles in its container
  ROUTER_MEM (the shard unit's MemoryMax)      max(0.375, 0.625 / shards) x RAM   160G for one router, 96G per shard of 4 (caps, not
                                                                             reservations: the memgate and the runaway guard hold the host)
  memgate claim = reserve (MB)                 min(0.75 x RAM / (all compiles at once), ROUTER_MEM / 4), in [3000, 8000], rounded
                                               down to 1000 (the gate admits a compile when claim + reserve fit in the unit)
  auto-brief row x compile workers             rows x max(1, min(4, vCPU / shards / rows))   ~1 brief compile per vCPU: 15 x 4 on 64 vCPU
  auto-brief container memory                  = ROUTER_MEM
  session container memory (--agent-docker-memory)  clamp(0.1875 x RAM, 2 claims + reserve + 2, 48) GB (the container's own gate)
  guard MIN_AVAIL_MB (runaway guard pressure)  min(12000, 0.15 x RAM)

    python3 harness/host_knobs.py [--shards 4] [--rows 15] [--vcpu N --mem-gb G --smt 0/1]   (prints the knobs and why)"""
from __future__ import annotations

import argparse, json, math, os
from pathlib import Path

ANCHOR = {"vcpu": 64, "smt": True, "cores": 32, "mem_gb": 256}
MIN_HOST = {"vcpu": 16, "mem_gb": 64}     # the README's minimum: below it the run still works, only slower (warned)
SESSIONS_MAX = 16                         # OpenRouter callers at once over all shards (12 measured with 0 rate limits; 4 x 4 planned)
SLOTS_MAX = 32                            # the compile-throughput knee on the anchor (infra/azure/README.md, compile concurrency)


def host() -> dict:
    """{vcpu, smt, cores, mem_gb} of this machine (SMT from /sys/devices/system/cpu/smt/active; without the file: no SMT)."""
    vcpu = os.cpu_count() or 1
    try:
        smt = Path("/sys/devices/system/cpu/smt/active").read_text().strip() == "1"
    except OSError:
        smt = False
    mem_kb = 0
    try:
        for l in Path("/proc/meminfo").read_text().splitlines():
            if l.startswith("MemTotal:"):
                mem_kb = int(l.split()[1]); break
    except OSError:
        pass
    return {"vcpu": vcpu, "smt": smt, "cores": max(1, vcpu // 2 if smt else vcpu), "mem_gb": round(mem_kb / 1024 / 1024, 1)}


def installed_gb(mem_gb: float) -> int:
    """The installed RAM a MemTotal reading (GB) stands for: rounded up to a multiple of 16 GB (8 GB below 32 GB). Review 2026-10-27:
    MemTotal leaves out the kernel's and firmware's reservations, so a 256 GB host reads ~250 and int(250 / 16) = 15 sessions gave
    the anchor's 4 shards 3 sessions each; an installed size already on the grid (the anchor's 256, 64) is kept as it is."""
    m = max(1.0, float(mem_gb)); g = 16 if m >= 32 else 8
    return int(math.ceil(m / g - 1e-9)) * g


def knobs(h: dict, shards: int, rows: int, over: dict | None = None) -> dict:
    """The knobs for `shards` routers of at most `rows` rows each on host h. over: {knob: value} replaces a derived value (None = derive).
    Returns {knob: value, ..., "why": {knob: text}, "host": h, "warnings": [...]}."""
    over = {k: v for k, v in (over or {}).items() if v is not None}
    S, R = max(1, int(shards)), max(1, int(rows))
    vcpu, mem = int(h["vcpu"]), installed_gb(h["mem_gb"])   # review 2026-10-27: the installed RAM, not MemTotal (installed_gb)
    cores = int(h.get("cores") or (vcpu // 2 if h.get("smt") else vcpu))
    why, k = {}, {}

    def put(name, val, text):
        if name in over:
            k[name], why[name] = over[name], f"override (derived: {val}; {text})"
        else:
            k[name], why[name] = val, text
    put("compile_slots", max(1, min(SLOTS_MAX, cores) // S), f"min({SLOTS_MAX}, {cores} cores) / {S} shard(s)")
    put("jobs", max(1, min(R, 2 * int(k["compile_slots"]))), f"min({R} rows, 2 x {k['compile_slots']} slots)")
    total = max(1, min(SESSIONS_MAX, cores // 2, int(mem // 16)))
    put("workers", max(1, min(R, total // S if total >= S else 1)), f"min({R} rows, {total} sessions over all shards / {S}); "
        f"total = min({SESSIONS_MAX}, {cores} cores / 2, {mem:g} GB / 16)")
    rm = int(max(0.375, 0.625 / S) * mem)
    put("router_mem_gb", max(4, rm), f"max(0.375, 0.625 / {S}) x {mem:g} GB")
    conc = S * int(k["compile_slots"]) + S * int(k["workers"])
    claim = int(min(8000, max(3000, (min(0.75 * mem * 1024 / max(1, conc), int(k["router_mem_gb"]) * 1024 / 4)) // 1000 * 1000)))
    put("memgate_claim_mb", claim, f"min(0.75 x {mem:g} GB / {conc} compiles at once ({S} x {k['compile_slots']} slots + {S} x {k['workers']} "
        f"sessions), ROUTER_MEM {k['router_mem_gb']}G / 4: a claim + reserve fits twice in the unit), in [3000, 8000]")
    put("memgate_reserve_mb", int(k["memgate_claim_mb"]), "= the claim")
    rw = max(1, min(R, vcpu // S))
    put("brief_row_workers", rw, f"min({R} rows, {vcpu} vCPU / {S})")
    put("brief_compile_workers", max(1, min(4, vcpu // S // max(1, int(k["brief_row_workers"])))),
        f"max(1, min(4, {vcpu} vCPU / {S} / {k['brief_row_workers']} row workers))")
    put("brief_docker_memory_gb", int(k["router_mem_gb"]), "= ROUTER_MEM")
    # a container's own gate admits a compile when claim + reserve fit next to the grants still ramping (60 s): a session's probe compile
    # is followed at once by its library-lead compiles, so room for one ramping claim more (b66 rehearsal: 12g held a 2nd compile 55-120 s)
    gate = math.ceil((2 * int(k["memgate_claim_mb"]) + int(k["memgate_reserve_mb"])) / 1024) + 2
    put("agent_docker_memory_gb", int(min(48, max(gate, 0.1875 * mem))), f"clamp(0.1875 x {mem:g} GB, 2 claims + reserve + 2 = {gate}, 48)")
    put("guard_min_avail_mb", int(min(12000, 0.15 * mem * 1024)), f"min(12000, 0.15 x {mem:g} GB)")
    warn = []
    for n in ("agent_docker_memory_gb", "brief_docker_memory_gb", "router_mem_gb"):   # an override below the memgate's need: every compile
        if int(k[n]) * 1024 < int(k["memgate_claim_mb"]) + int(k["memgate_reserve_mb"]) + 1024:   # there waits RELAX_S (600 s) first
            warn.append(f"{n} {k[n]}G is below memgate claim + reserve + 1 GB: compiles there wait the gate's relax time (600 s) first")
    if vcpu < MIN_HOST["vcpu"] or mem < MIN_HOST["mem_gb"] * 0.95:
        warn.append(f"below the minimum host ({MIN_HOST['vcpu']} vCPU / {MIN_HOST['mem_gb']} GB): the run works but is slower")
    if S * int(k["router_mem_gb"]) > 1.6 * mem:
        warn.append(f"{S} x ROUTER_MEM {k['router_mem_gb']}G is far above RAM {mem:g} GB (caps, not reservations; the memgate holds the host)")
    return dict(k, why=why, host=dict(h, cores=cores, mem_installed_gb=mem), shards=S, rows=R, warnings=warn)


def env_of(k: dict) -> dict:
    """The environment variables of a shard's router unit (the memgate knobs reach the containers through hx_heldout DOCKER_PASS_*)."""
    return {"LRA_MEMGATE_CLAIM_MB": str(k["memgate_claim_mb"]), "LRA_MEMGATE_RESERVE_MB": str(k["memgate_reserve_mb"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--shards", type=int, default=4); ap.add_argument("--rows", type=int, default=15)
    ap.add_argument("--vcpu", type=int); ap.add_argument("--mem-gb", type=float); ap.add_argument("--smt", type=int, choices=[0, 1])
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    h = host()
    if a.vcpu or a.mem_gb or a.smt is not None:
        smt = bool(a.smt) if a.smt is not None else h["smt"]
        vcpu = a.vcpu or h["vcpu"]
        h = {"vcpu": vcpu, "smt": smt, "cores": max(1, vcpu // 2 if smt else vcpu), "mem_gb": a.mem_gb or h["mem_gb"]}
    k = knobs(h, a.shards, a.rows)
    if a.json:
        print(json.dumps(k, indent=1)); return 0
    print(f"host {h['vcpu']} vCPU ({k['host']['cores']} cores{', SMT' if h['smt'] else ''}), {k['host']['mem_installed_gb']} GB installed "
          f"(MemTotal {h['mem_gb']} GB); {k['shards']} shard(s) x <= {k['rows']} rows")
    for n, t in k["why"].items():
        print(f"  {n:24s} {str(k[n]):>6s}   {t}")
    for w in k["warnings"]:
        print("  WARNING:", w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
