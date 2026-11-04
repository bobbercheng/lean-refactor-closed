#!/usr/bin/env python3
"""Upload a submission to the Lean Refactor Arena through its Gradio API (no gradio_client dependency).

  python3 submit/upload.py send   --file submit/candidates/X.jsonl [--track open|closed]
  python3 submit/upload.py report --models "..." --effort "..."      # public "Model & reasoning" self-report
  python3 submit/upload.py view                                      # the account's submissions (status/scores)
  --user NAME --key-file PATH   another username (default Vexorium, ~/.config/vexorium/lra_submission_key)
  send --new-user               FIRST submission of a new username: the key is sent empty and the key the Space issues (it reserves
                                the username) is saved to --key-file (mode 600, must not exist yet); the raw response is kept next
                                to it (mode 600) so the key is recoverable if parsing misses it. The key is never printed.
"""
from __future__ import annotations
import argparse, json, os, pathlib, re, sys, urllib.request, uuid

BASE = "https://delta-lab-ai-lean-refactor-arena.hf.space/gradio_api"
CONF = pathlib.Path("~/.config/vexorium").expanduser()


def call(endpoint: str, data: list, timeout: int = 600):
    req = urllib.request.Request(f"{BASE}/call/{endpoint}", data=json.dumps({"data": data}).encode(), headers={"content-type": "application/json"})
    eid = json.load(urllib.request.urlopen(req, timeout=60))["event_id"]
    sse = urllib.request.urlopen(f"{BASE}/call/{endpoint}/{eid}", timeout=timeout).read().decode()
    events = [l[5:].strip() for l in sse.splitlines() if l.startswith("data:")]
    return json.loads(events[-1]) if events else sse


def upload(path: pathlib.Path) -> dict:
    boundary = uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{path.name}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"{BASE}/upload", data=body, headers={"content-type": f"multipart/form-data; boundary={boundary}"})
    server_path = json.load(urllib.request.urlopen(req, timeout=120))[0]
    return {"path": server_path, "orig_name": path.name, "meta": {"_type": "gradio.FileData"}}


def write_secret(p: pathlib.Path, text: str) -> None:
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", default="Vexorium"); ap.add_argument("--key-file", default=str(CONF / "lra_submission_key"))
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("send"); s.add_argument("--file", required=True); s.add_argument("--track", choices=["open", "closed"], default="open")
    s.add_argument("--new-user", action="store_true")
    r = sub.add_parser("report"); r.add_argument("--models", required=True); r.add_argument("--effort", default="")
    sub.add_parser("view")
    a = ap.parse_args()
    kf = pathlib.Path(a.key_file).expanduser()
    if getattr(a, "new_user", False):
        assert not kf.exists(), f"{kf} exists: --new-user is only for a username's first submission"
        key = ""
    else:
        key = kf.read_text().strip()
        assert key, f"empty key in {kf}"
    if a.cmd == "send":
        f = upload(pathlib.Path(a.file))
        out = call("verify_and_submit", [a.user, key, "Open-source LLM" if a.track == "open" else "Closed-source LLM", f])
    elif a.cmd == "report":
        out = call("save_self_report", [a.user, key, a.models, a.effort])
    else:
        out = call("view_submissions", [a.user, key])
    s = json.dumps(out, ensure_ascii=False)
    if key:
        assert key not in s, "refusing to print a response that echoes the key"
    else:   # first submission: capture the issued key, keep the raw response, print a redacted response
        write_secret(kf.with_name(kf.name + ".first_response.json"), s)
        tok = lambda t: re.search(r"[A-Za-z]", t) and re.search(r"[0-9]", t)   # a key mixes letters and digits; words and usernames do not
        cands = [t for t in re.findall(r"`([A-Za-z0-9_\-]{12,})`", s) if tok(t)] or \
                [t for m in re.finditer(r"(?i)key", s) for t in re.findall(r"[A-Za-z0-9_\-]{16,}", s[m.end():m.end() + 160]) if tok(t)]
        if cands:
            write_secret(kf, cands[0] + "\n")
            s = s.replace(cands[0], "<issued key saved to " + str(kf) + ">")
            print(f"issued key captured ({len(cands[0])} chars) -> {kf} (mode 600)", file=sys.stderr)
        else:
            print(f"WARNING: no key found in the response; raw response kept (mode 600) at {kf}.first_response.json", file=sys.stderr)
            s = "<response withheld: it may contain the key; see the mode-600 file>"
    print(s if a.cmd == "view" else s[:4000])


if __name__ == "__main__":
    main()
