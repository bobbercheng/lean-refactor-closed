#!/usr/bin/env python3
"""Spend guard of the warm-up clean recheck (docs/warmup_clean_recheck.md): every 120 s, reads the OpenRouter account balance and the Sol
key's usage (never prints the key) and the ladders' own ledgers; stops both ladder units if the balance falls under FLOOR. Bounded: exits
when both ladders are inactive, or after 13 h (unit RuntimeMaxSec). Log: probe/heldout/wuclean-guard.log."""
import argparse, json, pathlib, subprocess, sys, time, urllib.request

MAIN = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(MAIN))
from harness.agent import MODEL_PRESETS  # noqa: E402

FLOOR = 2.0
_ap = argparse.ArgumentParser()   # 2026-10-14: any set of units (the Argon arm joined the clean recheck), one log per guard
_ap.add_argument("--units", default="lra-hx-wuclean1,lra-hx-wuclean2"); _ap.add_argument("--log", default="probe/heldout/wuclean-guard.log")
_ap.add_argument("--yield-unit", default=None, help="2026-10-14: stop THIS unit alone (it resumes later) when the balance cannot cover the "
                 "Sol recheck's worst case (remaining per-row caps of the running Sol ladders) plus the floor")
_a = _ap.parse_args()
UNITS = [u for u in _a.units.split(",") if u]
LOG = MAIN / _a.log
KEY = pathlib.Path(MODEL_PRESETS["gpt-6.1-sol"]["key"]).expanduser().read_text().strip()   # /credits is account-wide: any key reads it


def get(path: str) -> dict:
    req = urllib.request.Request(f"https://openrouter.ai/api/v1/{path}", headers={"Authorization": f"Bearer {KEY}"})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]


def ledger() -> float:
    tot = 0.0
    for wt in (pathlib.Path.home() / "source/lra-ab").glob("wuclean-*-hx/harness/hwork"):   # every clean arm
        arm = wt.parent.parent.name[len("wuclean-"):-len("-hx")]
        for st in list(wt.glob(f"wuclean-{arm}/*/state.json")) + list(wt.glob(f"wuclean-{arm}-fresh/*/state.json")):
            try:
                d = json.loads(st.read_text())
            except (OSError, ValueError):
                continue
            if d.get("lineage") != "fresh":   # a fresh lineage starts with the main lineage's spend: count the main lineage only
                tot += float(d.get("api_spend") or 0)
    return tot


def sol_remaining() -> float:
    """Worst case still to spend by the running Sol ladders: per row $2.85 minus its main-lineage spend (in-flight fresh spend is inside)."""
    rem = 0.0
    for i, arm in (("1", "solclean1"), ("2", "solclean2")):
        if not active(f"lra-hx-wuclean{i}"):
            continue
        sp = [float(json.loads(st.read_text()).get("api_spend") or 0)
              for st in (pathlib.Path.home() / f"source/lra-ab/wuclean-{arm}-hx/harness/hwork/wuclean-{arm}").glob("*/state.json")]
        rem += sum(max(0.0, 2.85 - x) for x in sp) + 2.85 * (15 - len(sp))
    return rem


def say(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def active(u: str) -> bool:
    return subprocess.run(["systemctl", "--user", "is-active", "--quiet", u]).returncode == 0


u0 = None
while True:
    try:
        c, k = get("credits"), get("key")
        bal = float(c["total_credits"]) - float(c["total_usage"])
        u0 = k["usage"] if u0 is None else u0
        say(f"balance ${bal:.2f} | Sol key usage +${k['usage'] - u0:.2f} since guard start | ladder ledgers ${ledger():.2f}")
        if _a.yield_unit and active(_a.yield_unit) and bal < sol_remaining() + FLOOR:
            say(f"balance ${bal:.2f} cannot cover the Sol recheck's worst case ${sol_remaining():.2f} + floor: stopping {_a.yield_unit} alone (resumable)")
            subprocess.run(["systemctl", "--user", "stop", _a.yield_unit])
        # 2026-10-14 (the A/B hit the Sol key's $190 total limit: every call 403, and the ladder kept launching rounds): the preset key's
        # own limit is a floor too
        if k.get("limit_remaining") is not None and float(k["limit_remaining"]) < 1.0:
            say(f"key limit nearly exhausted (${float(k['limit_remaining']):.2f} left of ${k.get('limit')}): stopping {', '.join(UNITS)}")
            for u in UNITS:
                subprocess.run(["systemctl", "--user", "stop", u])
            break
        if bal < FLOOR:
            say(f"balance under ${FLOOR:.2f}: stopping {', '.join(UNITS)}")
            for u in UNITS:
                subprocess.run(["systemctl", "--user", "stop", u])
            break
    except Exception as e:  # noqa: BLE001
        say(f"check failed: {type(e).__name__}: {e}")
    if not any(active(u) for u in UNITS):
        say("both ladders inactive; guard exits")
        break
    time.sleep(120)
