// Watches one live-video page headless and writes one JSON line a second: the
// page's console trail, its video-session HTTP responses, and the browser's own
// WebRTC inbound-video statistics (frames decoded and dropped, freezeCount and
// totalFreezesDuration, packets lost, NACKs, keyframe requests, jitter buffer).
// No clicks; exits when done.
//
//   node watch.mjs <seconds> <url> [tag]
//
// Needs Playwright (npm i playwright) and a Chrome install. If the page needs a
// sign-in, save your own session once with Playwright's storageState and point
// WATCH_STATE at that file; it holds your cookies, so never share it.
// The page-specific bits (which console lines to keep, which responses are the
// video session, the three text selectors) match the page we watched; change
// them for yours. Output: <tag>-<ISO time>.jsonl beside this script.
import fs from "node:fs";
import path from "node:path";
import { chromium } from "playwright";
const secs = Number(process.argv[2]);
const url = process.argv[3];
if (!Number.isFinite(secs) || secs <= 0 || !url) {
  console.error("usage: node watch.mjs <seconds> <url> [tag]");
  process.exit(2);
}
const here = path.dirname(new URL(import.meta.url).pathname);
const tag = process.argv[4] ?? "run";
const out = path.join(here, `${tag}-${new Date().toISOString().replace(/[:.]/g, "-")}.jsonl`);
const w = fs.createWriteStream(out, { mode: 0o600 });
const put = (o) => w.write(JSON.stringify({ t: Date.now(), ...o }) + "\n");
const browser = await chromium.launch({ channel: "chrome", headless: true, args: ["--autoplay-policy=no-user-gesture-required"] });
const state = process.env.WATCH_STATE;
const ctx = await browser.newContext({ ...(state ? { storageState: state } : {}), viewport: { width: 1440, height: 900 } });
await ctx.addInitScript(() => {
  const Orig = window.RTCPeerConnection;
  window.__pcs = [];
  window.RTCPeerConnection = function (...a) { const pc = new Orig(...a); window.__pcs.push(pc); return pc; };
  window.RTCPeerConnection.prototype = Orig.prototype;
  Object.assign(window.RTCPeerConnection, Orig);
});
const page = await ctx.newPage();
page.on("console", (m) => {
  const text = m.text();
  if (/^\[(player|hls)\]/.test(text) || m.type() === "error") put({ ev: "console", type: m.type(), text: text.split("\n")[0].slice(0, 400) });
});
page.on("pageerror", (e) => put({ ev: "pageerror", text: String(e).split("\n")[0].slice(0, 300) }));
page.on("response", (r) => {
  const u = r.url();
  if (!/\/api\/(whep|assets\/[^/]+\/hls)/.test(u)) return;
  const kind = /\/hls\//.test(u) ? "hls" : /\/v[0-9a-f]{20,}$/.test(u) ? "session" : "open";
  if (kind === "session" && r.request().method() === "GET" && r.status() === 204) { counts.sample++; return; }
  put({ ev: "http", method: r.request().method(), kind, status: r.status() });
});
const counts = { sample: 0 };
await page.goto(url, { waitUntil: "domcontentloaded" }).catch((e) => put({ ev: "goto_error", text: String(e).split("\n")[0] }));
put({ ev: "start", secs });
const end = Date.now() + secs * 1000;
while (Date.now() < end) {
  const snap = await page.evaluate(async () => {
    const text = (sel) => document.querySelector(sel)?.textContent?.replace(/\s+/g, " ").trim() ?? null;
    const v = document.querySelector("video");
    const pcs = (window.__pcs ?? []).filter((p) => p.connectionState !== "closed");
    let rtc = null;
    const pc = pcs.at(-1);
    if (pc) {
      const rep = await pc.getStats();
      let inb = null, pair = null;
      rep.forEach((s) => {
        if (s.type === "inbound-rtp" && (s.kind === "video" || s.mediaType === "video")) inb = s;
        if (s.type === "candidate-pair" && s.nominated) pair = s;
      });
      rtc = {
        state: pc.connectionState, ice: pc.iceConnectionState,
        ...(inb ? { bytes: inb.bytesReceived, frames: inb.framesDecoded, dropped: inb.framesDropped, key: inb.keyFramesDecoded, lost: inb.packetsLost, nack: inb.nackCount, pli: inb.pliCount, freezes: inb.freezeCount, freeze_s: inb.totalFreezesDuration, jb_delay: inb.jitterBufferDelay, jb_emitted: inb.jitterBufferEmittedCount, jb_target: inb.jitterBufferTargetDelay, jb_min: inb.jitterBufferMinimumDelay, fps: inb.framesPerSecond } : {}),
        ...(pair ? { rtt: pair.currentRoundTripTime } : {}),
      };
    }
    return {
      pcs_open: pcs.length, pcs_ever: (window.__pcs ?? []).length, rtc,
      video: v ? { t: v.currentTime, ready: v.readyState, paused: v.paused, w: v.videoWidth } : null,
      head: text('[data-testid="link-quality-row"]'),
      chain: text('[data-testid="link-chain"]'),
      overlay: text('[data-testid="live-overlay-message"]') ?? (document.body.innerText.match(/No signal[^\n]*|Connecting[^\n]*|Waiting for video[^\n]*|Stream ended[^\n]*/)?.[0] ?? null),
    };
  }).catch((e) => ({ eval_error: String(e).split("\n")[0].slice(0, 200) }));
  put({ ev: "tick", samples: counts.sample, ...snap });
  await page.waitForTimeout(1000);
}
put({ ev: "end" });
await browser.close();
w.end();
console.log(out);
