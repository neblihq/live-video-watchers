# live-video-watchers

Scripts for finding where live drone video gets lost on its way from the aircraft to a viewer's screen. We wrote them while chasing a stutter on a DJI Matrice 4E and RC Plus 2 controller, and we tell that story here: [Our drone video kept freezing for seconds at a time](https://nebli.ai/blog/drone-video-freezing-controller-wifi/).

If your live video freezes for a second or more at a time, start with the five-minute check below. You need nothing but a laptop on the same Wi-Fi as the controller. The full setup after it is for engineers who want every layer on one timeline.

These are the scripts as we ran them on November 10, 2026, with our addresses and ids removed. They are not a Nebli product and come with no support. They are MIT licensed: use them however you like.

## The five-minute check: ping the controller while you stream

1. Find the controller's address on your Wi-Fi. Your router's list of connected devices shows it.
2. Start streaming from the controller as you normally would.
3. On a laptop on the same Wi-Fi, ping the controller five times a second for a few minutes:

   - macOS: `ping -i 0.2 <controller address>`
   - Linux: `ping -i 0.2 -D <controller address>`
   - Windows: `ping -t <controller address>` (once a second is the fastest Windows allows)

4. Watch for replies that suddenly take a second or more, or stop altogether, at the moments the video freezes.

If the pings stall when the video stalls, the controller or its Wi-Fi is holding its traffic, and a better server or player won't help. If the pings stay steady while the video freezes, look further down the line: the internet link, the streaming service, the player.

For a control, ping a second device on the same Wi-Fi at the same time. If both stall together, suspect the network rather than the controller.

## The full setup: four watchers on one clock

| File | What it does |
|---|---|
| `watch-all.sh` | Pings the controller, the gateway and, if you give it one, a second device on the same access-point radio, five times a second. Over adb it also samples the controller's own Wi-Fi bytes and RTMP connection ten times a second, saves its Android log through `mask.pl`, and measures how far its clock is from the laptop's. |
| `mask.pl` | Hides stream keys, tokens, passwords and signed URLs in a log, line by line, before anything is written to disk. |
| `watch.mjs` | Opens a live-video page in headless Chrome and writes, once a second, the browser's own statistics for the incoming video: frames decoded and dropped, freezes and their total length, packets lost. |
| `timeline.py` | Puts the ingest's gap lines, the ping blackouts and the viewer's freezes on one timeline and counts how often they line up. |
| `compare.py` | For each time window you name: holes per minute, share of time in holes, longest hole, slowest pings. |

### Running them

    ./watch-all.sh --controller <controller addr> --gateway <gateway addr> [--peer <addr>] --out run1
    node watch.mjs 900 '<live page URL>'            # WATCH_STATE=<your storageState file> if the page needs a sign-in
    python3 timeline.py run-<time>.jsonl --ingest-log ingest.log --pings run1/ping-rc.txt --peer <controller addr> --all
    python3 compare.py --ingest-log ingest.log --date 2026-11-10 'ch 104|<controller addr>|run1|15:14:30|15:55:00'

You need macOS `ping` (for its timestamps; on Linux use `ping -D` and change the two parsers), `adb` with network debugging turned on on the controller, Python 3.9 or later, Node 18 or later with Playwright, and Chrome.

One piece is not here: the ingest, the server that receives the controller's RTMP stream. Ours logged a line every time no bytes arrived for 0.3 s or more. Any RTMP server you can make log the gap between reads will do, written as JSON lines with a "time" field in this format:

    [dbg] SOCKET IDLE <peer>: nothing arrived for 3.47s, then 2896 bytes in one read

## What the words mean

- **Ping blackout:** a reply slower than 150 ms. The replies queued behind it, each over 150 ms and smaller than the one before, belong to the same blackout; its length is the first reply's round trip.
- **Hole:** no bytes reached the ingest on the controller's RTMP connection for 0.3 s or more.
- **Freeze:** whatever the browser counts as one (`freezeCount` in its WebRTC statistics).

## Things to know before you trust the numbers

- Everything except the controller's own log has to carry the same machine's clock. The controller's log runs on its own clock; `watch-all.sh` writes the offset to `clock.txt`, and you apply it by hand.
- The adb sampling travels over the same Wi-Fi you are measuring. It is a small amount of traffic, but it is there.
- `watch.mjs` was written for the page we watched: it keeps console lines that start with `[player]` and treats requests under `/api/whep` as the video session. Change both for your player.
- The storageState file `watch.mjs` signs in with holds your cookies. Never publish it.
