#!/usr/bin/env python3
"""One timeline from every watcher: holes at the ingest, controller ping
blackouts, and what a headless viewer saw, sorted on one clock.

Usage:
  timeline.py <run.jsonl> --ingest-log ingest.log --pings ping-rc.txt --peer <address> \
      [--tz America/New_York] [--all]

  run.jsonl   the headless viewer's output (watch.mjs)
  --peer      the controller's address as it appears in the ingest log's lines
  --pings     macOS `ping --apple-time -i 0.2 <controller>` output
  --all       print every event; without it, only the player's and page's lines

All three inputs must carry the same machine's clock. A ping blackout is a reply
over 150 ms, with the queued replies behind it folded in (see compare.py).
"""
import json, re, sys, datetime, zoneinfo, argparse
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("run")
ap.add_argument("--ingest-log", required=True)
ap.add_argument("--pings", required=True)
ap.add_argument("--peer", required=True)
ap.add_argument("--tz", default="America/New_York")
ap.add_argument("--all", action="store_true")
args = ap.parse_args()
ET = zoneinfo.ZoneInfo(args.tz)
RCIP = args.peer
f = lambda t: datetime.datetime.fromtimestamp(t, ET).strftime("%-I:%M:%S.%f")[:-5]
run = [json.loads(l) for l in open(args.run) if l.strip()]
t0, t1 = run[0]["t"] / 1000, run[-1]["t"] / 1000
ev = []  # (time, source, text)
# 1. ingest: socket idles and media-clock jumps from the RC
idle = []
for l in open(args.ingest_log, errors="ignore"):
    if RCIP not in l or "[dbg]" not in l: continue
    try: j = json.loads(l)
    except Exception: continue
    ts = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), j["time"])
    t = datetime.datetime.fromisoformat(ts).timestamp()
    if not (t0 - 5 <= t <= t1 + 5): continue
    m = re.search(r"SOCKET IDLE .*?nothing arrived for ([\d.]+)s, then (\d+) bytes", j["msg"])
    if m:
        d = float(m.group(1)); idle.append((t - d, d)); ev.append((t - d, "INGEST", f"nothing from the controller for {d:.2f}s"))
    m = re.search(r"PTS JUMP .*?stepped ([+-][\d.]+)s", j["msg"])
    if m: ev.append((t, "INGEST", f"controller skipped {m.group(1)}s of video"))
# 2. RC blackouts from the Mac's 5 Hz ping
pr = []
day = datetime.datetime.fromtimestamp(t0, ET).date()
try:
    for l in open(args.pings):
        m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d+) .*time=([\d.]+)", l)
        if not m: continue
        t = datetime.datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)[:6].ljust(6, "0")), tzinfo=ET).timestamp()
        if t0 - 5 <= t <= t1 + 5: pr.append((t, float(m.group(5))))
except FileNotFoundError: pass
black = []; i = 0
while i < len(pr):
    if pr[i][1] > 150:
        j = i
        while j + 1 < len(pr) and pr[j + 1][1] > 150 and pr[j + 1][1] < pr[j][1]: j += 1
        d = pr[i][1] / 1000; black.append((pr[i][0] - d, d)); ev.append((pr[i][0] - d, "PING", f"controller unreachable {d:.2f}s")); i = j + 1
    else: i += 1
# 3. the viewer: console trail, session requests, per-second WebRTC
ticks = [r for r in run if r["ev"] == "tick" and r.get("rtc")]
for r in run:
    t = r["t"] / 1000
    if r["ev"] == "console": ev.append((t, "PLAYER", re.sub(r'"viewer":"?[^,]*,?', "", r["text"])[:150]))
    elif r["ev"] == "http": ev.append((t, "PLAYER", f"http {r['method']} {r['kind']} -> {r['status']}"))
    elif r["ev"] in ("pageerror", "goto_error"): ev.append((t, "PAGE", r["text"][:120]))
prev = None; frozen = []; words = []
for r in ticks:
    t = r["t"] / 1000; c = r["rtc"]
    if prev and c.get("frames") is not None and prev["rtc"].get("frames") is not None:
        df = c["frames"] - prev["rtc"]["frames"]; db = c["bytes"] - prev["rtc"]["bytes"]
        if df <= 2 and db >= 0: frozen.append(t)
        if c.get("freezes", 0) > prev["rtc"].get("freezes", 0): ev.append((t, "VIEWER", f"browser counted a freeze (+{c['freeze_s'] - prev['rtc'].get('freeze_s', 0):.2f}s)"))
    w = (r.get("head") or "")[:60]
    if not words or words[-1][1] != w: words.append((t, w))
    prev = r
# runs of seconds with (almost) no decoded frame
runs = []
for t in frozen:
    if runs and t - runs[-1][1] < 1.6: runs[-1][1] = t
    else: runs.append([t, t])
for a, b in runs: ev.append((a, "VIEWER", f"no new frame on screen for ~{b - a + 1:.0f}s"))
ev.sort()
n = lambda src: sum(1 for e in ev if e[1] == src)
print(f"window {f(t0)} - {f(t1)} ET ({t1 - t0:.0f}s)")
print(f"ingest idles >=0.3s: {len(idle)} (total {sum(d for _, d in idle):.1f}s) | controller ping blackouts: {len(black)} (total {sum(d for _, d in black):.1f}s) | viewer frozen stretches: {len(runs)} | player sessions opened: {sum(1 for r in run if r['ev']=='http' and r['kind']=='open')}")
if ticks:
    a, b = ticks[0]["rtc"], ticks[-1]["rtc"]
    print(f"viewer totals: frames decoded {b.get('frames',0)-a.get('frames',0)}, dropped {b.get('dropped',0)-a.get('dropped',0)}, freezes {b.get('freezes',0)-a.get('freezes',0)} ({b.get('freeze_s',0)-a.get('freeze_s',0):.1f}s), packets lost {b.get('lost',0)-a.get('lost',0)}, nack {b.get('nack',0)-a.get('nack',0)}, keyframe requests {b.get('pli',0)-a.get('pli',0)}")
# match: each ingest idle -> an RC blackout overlapping it? a viewer freeze within 3 s after?
hit_rc = sum(1 for (t, d) in idle if any(bt < t + d and bt + bd > t - 0.3 for bt, bd in black))
hit_v = sum(1 for (t, d) in idle if d >= 1 and any(t - 0.5 <= a <= t + d + 3 for a, _ in runs))
long_idle = sum(1 for _, d in idle if d >= 1)
print(f"of {len(idle)} ingest idles, {hit_rc} overlap a ping blackout; of {long_idle} idles of 1 s or more, {hit_v} are followed by a frozen picture within 3 s")
print("page word changes:", len(words))
if args.all:
    for t, src, text in ev: print(f"{f(t)}  {src:8s} {text}")
else:
    for t, src, text in [e for e in ev if e[1] in ("PLAYER", "PAGE")][:40]: print(f"{f(t)}  {src:8s} {text}")
