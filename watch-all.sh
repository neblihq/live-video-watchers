#!/bin/bash
# Samples everything around one live stream from a DJI RC Plus 2 (or any Android
# controller with adb over the network) until stopped with Ctrl-C:
#   ping-rc.txt    pings to the controller, 5 a second (who stops answering, and when)
#   ping-gw.txt    pings to the gateway, the control for the network itself
#   ping-peer.txt  pings to another device on the same access-point radio (optional control)
#   rc.txt         10 a second, from the controller itself: its Wi-Fi bytes sent and the
#                  kernel's TCP state for its RTMP connection (port 1935)
#   rc-logcat.log  the controller's Android log, passed through mask.pl first
#   clock.txt      the controller's clock minus this machine's, to line its log up
#
# Usage: watch-all.sh --controller <addr> --gateway <addr> [--peer <addr>] [--out <dir>]
#
# Needs macOS ping (for --apple-time; on Linux use `ping -D` and adjust the parsers),
# adb, python3, and adb over the network enabled on the controller (port 5555).
# The adb traffic rides the same Wi-Fi link being measured; it is small, but it is there.
# Addresses in the controller's socket lines are replaced with "ip:" before they are written.
set -u
CTRL="" GW="" PEER="" OUT="$(pwd)"
while [ $# -gt 0 ]; do
  case "$1" in
    --controller) CTRL="$2"; shift 2 ;;
    --gateway) GW="$2"; shift 2 ;;
    --peer) PEER="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "$CTRL" ] && [ -n "$GW" ] || { echo "usage: watch-all.sh --controller <addr> --gateway <addr> [--peer <addr>] [--out <dir>]" >&2; exit 2; }
HERE="$(cd "$(dirname "$0")" && pwd)"
ADB="${ADB:-adb}"
mkdir -p "$OUT"; cd "$OUT" || exit 1; umask 077
trap 'kill $(jobs -p) 2>/dev/null' EXIT

echo "waiting for the controller on the network"
until ping -c 1 -t 2 "$CTRL" >/dev/null 2>&1; do sleep 3; done
echo "controller reachable at $(date '+%H:%M:%S')"
until "$ADB" connect "$CTRL:5555" 2>&1 | grep -q "connected"; do sleep 3; done
until [ "$("$ADB" -s "$CTRL:5555" get-state 2>/dev/null)" = device ]; do sleep 2; done
echo "adb attached"

a=$(python3 -c 'import time;print(time.time())'); r=$("$ADB" -s "$CTRL:5555" shell 'date +%s.%N'); b=$(python3 -c 'import time;print(time.time())')
python3 -c "a,r,b=$a,$r,$b; print(f'controller clock minus this clock: {r-(a+b)/2:+.3f}s (round trip {b-a:.3f}s)')" | tee clock.txt

ping --apple-time -i 0.2 "$CTRL" > ping-rc.txt 2>&1 &
ping --apple-time -i 0.2 "$GW" > ping-gw.txt 2>&1 &
[ -n "$PEER" ] && { ping --apple-time -i 0.2 "$PEER" > ping-peer.txt 2>&1 & }

( : > rc-logcat.log
  while true; do
    "$ADB" connect "$CTRL:5555" >/dev/null 2>&1
    "$ADB" -s "$CTRL:5555" logcat -v threadtime -T 20 2>/dev/null | perl "$HERE/mask.pl" >> rc-logcat.log
    echo "--- logcat stream ended $(date '+%H:%M:%S'), reattaching ---" >> rc-logcat.log
    sleep 3
  done ) &

while true; do
  "$ADB" -s "$CTRL:5555" shell "while true; do t=\$(date +%s.%N); set -- \$(grep wlan0: /proc/net/dev); echo \"\$t \${10} \$(ss -tinoH state established '( dport = :1935 )' | tr '\n' ' ')\"; sleep 0.1; done" | sed -E 's/[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:/ip:/g' >> rc.txt 2>&1
  echo "adb shell ended at $(date '+%H:%M:%S'); reattaching"; sleep 3
  "$ADB" connect "$CTRL:5555" >/dev/null 2>&1
done
