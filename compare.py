#!/usr/bin/env python3
"""Per named window: holes in the bytes reaching the ingest, and ping blackouts to
the controller, side by side.

Usage:
  compare.py --ingest-log ingest.log --date 2026-11-10 [--tz America/New_York] \
      'name|peer|dir|HH:MM:SS|HH:MM:SS' ...

  peer   the controller's address as it appears in the ingest log's lines
  dir    a folder holding ping-rc.txt (pings to the controller) and, optionally,
         ping-gw.txt (pings to the gateway, the control)
  times  local wall-clock times on --date; the end may be "now"

Inputs:
  - the ingest log: JSON lines with a "time" (RFC 3339) and a "msg"; the lines
    used are "[dbg] SOCKET IDLE <peer>: nothing arrived for N s ..." and the
    one-second lines "[dbg] ... 1s ... socket N KB ...".
  - ping files from macOS `ping --apple-time -i 0.2 <address>`: each reply line
    starts with HH:MM:SS.ffffff and carries time=<ms>.

A ping blackout: a reply over 150 ms; following replies that are also over
150 ms and each smaller than the one before are the same blackout (they were
queued behind it). Its length is the first reply's round-trip time.
"""
import argparse, datetime, json, os, re, zoneinfo

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--ingest-log", required=True)
ap.add_argument("--date", required=True, help="the day the windows are on, YYYY-MM-DD")
ap.add_argument("--tz", default="America/New_York")
ap.add_argument("windows", nargs="+")
args = ap.parse_args()
TZ = zoneinfo.ZoneInfo(args.tz)
DAY = datetime.date.fromisoformat(args.date)

def T(s):
    if s == "now": return datetime.datetime.now().timestamp()
    h, m, x = map(int, s.split(":"))
    return datetime.datetime(DAY.year, DAY.month, DAY.day, h, m, x, tzinfo=TZ).timestamp()

LOG = []
for l in open(args.ingest_log, errors="ignore"):
    if "[dbg]" not in l: continue
    try: j = json.loads(l)
    except Exception: continue
    ts = re.sub(r"\.(\d+)", lambda m: "." + m.group(1)[:6].ljust(6, "0"), j["time"])
    LOG.append((datetime.datetime.fromisoformat(ts).timestamp(), j["msg"]))

def pings(path, a, b):
    pr = []; day = datetime.datetime.fromtimestamp(a, TZ).date()
    try:
        for l in open(path):
            m = re.match(r"(\d\d):(\d\d):(\d\d)\.(\d+) .*time=([\d.]+)", l)
            if not m: continue
            t = datetime.datetime(day.year, day.month, day.day, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4)[:6].ljust(6, "0")), tzinfo=TZ).timestamp()
            if a <= t <= b: pr.append((t, float(m.group(5))))
    except FileNotFoundError: pass
    black = []; i = 0
    while i < len(pr):
        if pr[i][1] > 150:
            j = i
            while j + 1 < len(pr) and pr[j + 1][1] > 150 and pr[j + 1][1] < pr[j][1]: j += 1
            black.append(pr[i][1] / 1000); i = j + 1
        else: i += 1
    return pr, black

print(f"{'window':34s} {'min':>5s} {'Mbps':>5s} {'holes>=1s/min':>13s} {'all holes/min':>13s} {'% in holes':>10s} {'longest':>8s} {'ping p99':>9s} {'blackout %':>10s} {'gw ctl':>6s}")
for arg in args.windows:
    name, peer, live, a, b = arg.split("|"); a, b = T(a), T(b)
    idle = []; secs = []
    for t, msg in LOG:
        if peer not in msg or not (a <= t <= b): continue
        m = re.search(r"SOCKET IDLE .*?for ([\d.]+)s", msg)
        if m: idle.append(float(m.group(1)))
        m = re.search(r"\] 1s .*?socket (\d+)KB", msg)
        if m: secs.append((t, int(m.group(1))))
    if len(secs) < 20: print(f"{name:34s} not enough data ({len(secs)} s)"); continue
    dur = secs[-1][0] - secs[0][0]
    pr, black = pings(os.path.join(live, "ping-rc.txt"), a, b)
    gw, gb = pings(os.path.join(live, "ping-gw.txt"), a, b)
    rt = sorted(p[1] for p in pr) or [0]
    print(f"{name:34s} {dur/60:5.1f} {8*sum(s[1] for s in secs)/dur/1000:5.1f} {sum(1 for d in idle if d>=1)/dur*60:13.1f} {len(idle)/dur*60:13.1f} {100*sum(idle)/dur:10.1f} {max(idle,default=0):7.1f}s {rt[int(.99*(len(rt)-1))]:8.0f}ms {100*sum(black)/dur:10.1f} {len(gb):6d}")
