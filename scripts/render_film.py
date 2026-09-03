#!/usr/bin/env python3
"""Render docs/film.html to video without touching the display or the disk.

Two earlier approaches each failed for a different reason, and both are worth
recording so neither gets retried.

`ffmpeg -f avfoundation` screen capture commandeers the display for the whole
four minutes and starts whenever Chrome happens to finish painting. That cost
a take: one attempt began 24s in and lost the title scene, and recovering it
needed a `blackdetect` pass to guess where the film actually started.

Headless Chrome over CDP fixed both of those, but the first version buffered
every frame to docs/.frames/ before assembling and filled the volume at frame
2,832 of 4,809.

So this version streams. Frames arrive from CDP in real time and go straight
into ffmpeg's stdin, one at a time, holding the most recent frame until the
next one arrives. Peak disk use is the output file, peak memory is one JPEG,
and the film's own clock starts a known 1200ms after load (see the JS in
build_film.py) so the trim point is arithmetic rather than a measurement.

    PYTHONPATH=. ./.venv/bin/python -m scripts.render_film
"""
from __future__ import annotations

import asyncio
import base64
import json
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
FILM = ROOT / "docs" / "film.html"
NARRATION = ROOT / "docs" / "narration.m4a"
OUT = ROOT / "docs" / "video.mp4"
STAGE = ROOT / "docs" / ".video_new.mp4"
FFLOG = ROOT / "logs" / "ffmpeg_render.log"
PROFILE = ROOT / "docs" / ".chrome-profile"

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9333
FPS = 30
LEAD_IN = 1.2          # must match the setTimeout in build_film.py's JS
TAIL = 1.5             # let the last scene sit before the cut
MIN_FREE_GB = 2.0


def runtime_seconds() -> int:
    """Total film length, from the same source the film itself is built from."""
    sys.path.insert(0, str(ROOT))
    from scripts.build_film import scenes
    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    return sum(s["t"] for s in scenes(proof))


def launch_chrome() -> subprocess.Popen:
    args = [
        CHROME,
        "--headless=new",
        f"--remote-debugging-port={PORT}",
        "--window-size=1920,1080",
        "--force-device-scale-factor=1",
        "--hide-scrollbars",
        f"--user-data-dir={PROFILE}",
        "about:blank",
    ]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version",
                                        timeout=1):
                return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("chrome did not open a debugging port")


def page_target() -> str:
    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=5) as r:
        tabs = json.loads(r.read())
    for t in tabs:
        if t.get("type") == "page":
            return t["webSocketDebuggerUrl"]
    raise SystemExit("no page target")


def open_encoder() -> subprocess.Popen:
    cmd = ["ffmpeg", "-y",
           "-f", "image2pipe", "-vcodec", "mjpeg", "-framerate", str(FPS), "-i", "-"]
    if NARRATION.exists():
        cmd += ["-i", str(NARRATION)]
    cmd += ["-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS)]
    if NARRATION.exists():
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += [str(STAGE)]
    # Keep ffmpeg's stderr. The previous version sent it to DEVNULL, so when
    # ffmpeg gave up on an empty pipe all that surfaced was a BrokenPipeError
    # from the writer, which says nothing about the cause.
    FFLOG.parent.mkdir(exist_ok=True)
    log = FFLOG.open("wb")
    return subprocess.Popen(cmd, stdin=subprocess.PIPE,
                            stdout=log, stderr=log)


async def capture(total: float) -> tuple[int, subprocess.Popen | None]:
    """Drive the film once, streaming a constant-rate timeline into ffmpeg.

    CDP only emits a frame when the page changes, so a still stats card sends
    almost nothing while a crossfade sends a burst. Holding the most recent
    frame until the next one arrives turns that irregular stream into exact
    30fps without buffering any of it.
    """
    import websockets

    ws_url = page_target()
    emitted = 0
    prev: bytes | None = None
    enc: subprocess.Popen | None = None

    async with websockets.connect(ws_url, max_size=None) as ws:
        seq = 0

        async def send(method: str, params: dict | None = None) -> int:
            nonlocal seq
            seq += 1
            await ws.send(json.dumps({"id": seq, "method": method,
                                      "params": params or {}}))
            return seq

        await send("Page.enable")
        await send("Runtime.enable")
        # --window-size counts browser chrome, which left the captured area at
        # 1920x993. The film's fit() scales to the viewport, so an off-size
        # viewport silently rescales the whole composition, and an odd height
        # is not even encodable in h264.
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1920, "height": 1080, "deviceScaleFactor": 1,
                    "mobile": False})
        await send("Page.navigate", {"url": FILM.as_uri()})

        # Anchor the timeline to the page's own clock, so the trim point is
        # the same instant the film's setTimeout was scheduled from.
        t_load = None
        while t_load is None:
            msg = json.loads(await ws.recv())
            if msg.get("method") == "Page.loadEventFired":
                rid = await send("Runtime.evaluate",
                                 {"expression": "Date.now()/1000",
                                  "returnByValue": True})
                while True:
                    m = json.loads(await ws.recv())
                    if m.get("id") == rid:
                        t_load = m["result"]["result"]["value"]
                        break

        t0 = t_load + LEAD_IN
        deadline = t0 + total + TAIL
        await send("Page.startScreencast", {"format": "jpeg", "quality": 92,
                                            "maxWidth": 1920, "maxHeight": 1080,
                                            "everyNthFrame": 1})
        print(f"  capturing {total:.0f}s headless, streaming to ffmpeg, "
              f"nothing on screen and nothing buffered")
        reported = 0.0

        while time.time() < deadline:
            try:
                msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
            except asyncio.TimeoutError:
                continue
            if msg.get("method") != "Page.screencastFrame":
                continue
            p = msg["params"]
            await send("Page.screencastFrameAck", {"sessionId": p["sessionId"]})
            ts = p["metadata"]["timestamp"]
            if ts < t0:
                continue                      # pre-roll, before the clock starts
            jpeg = base64.b64decode(p["data"])
            if prev is None:
                prev = jpeg
                enc = open_encoder()          # first frame in hand, safe to start
                continue
            if enc.poll() is not None:
                raise SystemExit(f"ffmpeg exited early (code {enc.returncode}), "
                                 f"see {FFLOG}")
            target = int((ts - t0) * FPS)
            while emitted < target:
                enc.stdin.write(prev)
                emitted += 1
            prev = jpeg
            if (ts - t0) - reported >= 30:
                reported = ts - t0
                print(f"    {reported:5.0f}s / {total:.0f}s   "
                      f"{emitted} frames encoded")

        await send("Page.stopScreencast")

    # Hold the closing frame out to the full runtime.
    target = int((total + TAIL) * FPS)
    while enc is not None and prev is not None and emitted < target:
        enc.stdin.write(prev)
        emitted += 1
    return emitted, enc


def main() -> int:
    if not FILM.exists():
        print("docs/film.html missing, run scripts.build_film first")
        return 1
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < MIN_FREE_GB:
        print(f"only {free_gb:.1f}GB free, need {MIN_FREE_GB}GB")
        return 1

    total = runtime_seconds()
    print(f"film runtime {total}s ({total // 60}:{total % 60:02d}), "
          f"{free_gb:.1f}GB free")

    proc = launch_chrome()
    enc = None
    try:
        emitted, enc = asyncio.run(capture(float(total)))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        if enc is not None:
            try:
                enc.stdin.close()
            except Exception:
                pass
            enc.wait()
        shutil.rmtree(PROFILE, ignore_errors=True)

    expected = int(total * FPS * 0.9)
    if enc is None or emitted < expected:
        print(f"only {emitted} frames encoded, expected at least {expected}; "
              f"{OUT.name} left untouched, see {FFLOG}")
        STAGE.unlink(missing_ok=True)
        return 1
    if not STAGE.exists() or STAGE.stat().st_size < 1_000_000:
        print(f"staged video is missing or too small; {OUT.name} left untouched, "
              f"see {FFLOG}")
        STAGE.unlink(missing_ok=True)
        return 1
    STAGE.replace(OUT)                        # only now does the real file change
    print(f"  {emitted} frames encoded at {FPS}fps")
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e6:.1f}MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
