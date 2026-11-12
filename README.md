# Four watchers on one clock

The scripts behind our post on a live-video stutter from a DJI RC Plus 2. They ran on
10 November 2026 against one controller, one aircraft on the ground and one home network.
They are what we used, cleaned of our addresses and ids; they are not a product.

| File | What it does |
|---|---|
| `watch-all.sh` | Pings the controller, the gateway and (optionally) a neighbour on the same access-point radio 5 times a second; over adb, samples the controller's own Wi-Fi bytes and RTMP socket 10 times a second, streams its Android log through `mask.pl`, and measures its clock offset. |
| `mask.pl` | Masks stream keys, tokens, passwords and signed URLs in a log stream, line by line, before anything is written. |
| `watch.mjs` | Opens a live-video page in headless Chrome (Playwright) and writes one JSON line a second with the browser's own WebRTC stats: frames decoded and dropped, freezeCount, totalFreezesDuration, packets lost, keyframe requests. |
| `timeline.py` | Puts the ingest's idle lines, the ping blackouts and the viewer's stats on one timeline and counts how often they line up. |
| `compare.py` | Per named time window: holes per minute, share of time in holes, longest hole, ping p99, blackout share. |

## Running them

    ./watch-all.sh --controller <controller addr> --gateway <gateway addr> [--peer <addr>] --out run1
    node watch.mjs 900 '<live page URL>'            # WATCH_STATE=<your storageState file> if it needs a sign-in
    python3 timeline.py run-<time>.jsonl --ingest-log ingest.log --pings run1/ping-rc.txt --peer <controller addr> --all
    python3 compare.py --ingest-log ingest.log --date 2026-11-10 'ch 104|<controller addr>|run1|15:14:30|15:55:00'

Needs macOS `ping` (for `--apple-time`; on Linux use `ping -D` and change the two parsers),
`adb` with adb over the network enabled on the controller, Python 3.9+, Node 18+ with
`playwright`, and Chrome.

## Definitions

- **Ping blackout:** a reply slower than 150 ms. The replies queued behind it, each over
  150 ms and smaller than the one before, are the same blackout; its length is the first
  reply's round-trip time.
- **Hole:** the ingest received no bytes on the controller's RTMP socket for 0.3 s or more.
  Our ingest logged one line per hole:
  `[dbg] SOCKET IDLE <peer>: nothing arrived for 3.47s, then 2896 bytes in one read`.
  The ingest itself is not in this set; any RTMP server you can make log the gap between
  reads that return bytes will do, in that line format, as JSON lines with a "time" field.
- **Freeze:** whatever the browser counts as one (`freezeCount` in the WebRTC statistics).

## Caveats

- One clock: the pings, the ingest log and the viewer must carry the same machine's time.
  The controller's own log is on its clock; `clock.txt` gives the offset to apply.
- The adb sampling rides the same Wi-Fi link being measured. It is small traffic, but it is there.
- `watch.mjs` keeps console lines starting `[player]` and treats responses under `/api/whep`
  as the video session: those match the page we watched. Change them for yours.
- `watch.mjs`'s storageState file holds your cookies: never publish it.
