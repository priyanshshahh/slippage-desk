"""Verify the submission package against the entry requirements.

verify_claims.py proves the numbers inside the deliverables agree with the
evidence. This proves the deliverables themselves are submittable: the right
formats, inside the stated limits, links that actually resolve, and no
placeholder left in a field.

Counts stated in docs/SUBMISSION.md are checked against the text they
describe, because both drifted the moment the copy was rewritten.

    PYTHONPATH=. ./.venv/bin/python scripts/check_submission.py
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
import urllib.error
import urllib.request

from engine.config import ROOT

SUB = ROOT / "docs" / "SUBMISSION.md"
SHORT_LIMIT = 255
VIDEO_MIN, VIDEO_MAX = 180.0, 300.0

rows: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str) -> None:
    rows.append((name, ok, detail))


def fenced(text: str, header: str) -> str:
    i = text.index(header)
    j = text.index("```", i) + 3
    return text[j:text.index("```", j)].strip()


def probe(path: pathlib.Path, *entries: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", ",".join(entries),
         "-of", "json", str(path)],
        capture_output=True, text=True)
    return json.loads(out.stdout or "{}")


def head(url: str) -> int:
    """Status code, following redirects, with no credentials attached.

    A judge opens these cold. Anything that needs a login is a failure here
    even though it loads perfectly in a browser that is already signed in.
    """
    req = urllib.request.Request(url, headers={"User-Agent": "submission-check"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:                              # noqa: BLE001
        return 0


def main() -> int:
    text = SUB.read_text()

    short = fenced(text, "## Short description")
    check("short description", len(short) <= SHORT_LIMIT,
          f"{len(short)}/{SHORT_LIMIT} chars")
    m = re.search(r"\((\d+) / 255 characters\)", text)
    check("short count stated", bool(m) and int(m.group(1)) == len(short),
          f"doc says {m.group(1) if m else 'nothing'}, actual {len(short)}")

    words = len(fenced(text, "## Long description").split())
    m = re.search(r"\*\((\d+) words", text)
    check("long count stated", bool(m) and int(m.group(1)) == words,
          f"doc says {m.group(1) if m else 'nothing'}, actual {words}")

    # No requirement is met by a field that still holds a placeholder.
    holes = re.findall(r"`(TODO|TBD|xxx+|<[^`>]+>)`", text, re.I)
    check("no placeholders", not holes, ", ".join(holes) if holes else "none")

    cover = ROOT / "docs" / "cover.png"
    if cover.exists():
        st = probe(cover, "stream=width,height")["streams"][0]
        w, h = st["width"], st["height"]
        check("cover 16:9", abs(w / h - 16 / 9) < 0.01, f"{w}x{h}")
    else:
        check("cover 16:9", False, "docs/cover.png missing")

    video = ROOT / "docs" / "video.mp4"
    if video.exists():
        dur = float(probe(video, "format=duration")["format"]["duration"])
        kinds = {s["codec_type"]
                 for s in probe(video, "stream=codec_type")["streams"]}
        check("video 3 to 5 min", VIDEO_MIN < dur < VIDEO_MAX,
              f"{int(dur // 60)}:{dur % 60:04.1f}")
        check("video has audio", "audio" in kinds, ", ".join(sorted(kinds)))
    else:
        check("video 3 to 5 min", False, "docs/video.mp4 missing")

    deck = ROOT / "docs" / "slides.pdf"
    check("slides pdf", deck.exists() and deck.read_bytes()[:4] == b"%PDF",
          f"{deck.stat().st_size // 1024} KB" if deck.exists() else "missing")

    lic = ROOT / "LICENSE"
    check("MIT licence", lic.exists() and "MIT License" in lic.read_text(),
          "present" if lic.exists() else "missing")

    check("paper account id", bool(re.search(r"`PA[A-Z0-9]{8,}`", text)),
          "stated")

    for label, url in re.findall(r"\| ([^|]*?URL|[^|]*?repository) *\| `(https://[^`]+)` *\|",
                                 text):
        code = head(url)
        check(label.strip().lower(), code == 200, f"{code}  {url}")

    width = max(len(n) for n, _, _ in rows)
    for name, ok, detail in rows:
        print(f"  [{'ok ' if ok else 'FAIL'}] {name:<{width}}  {detail}")

    bad = [n for n, ok, _ in rows if not ok]
    if bad:
        print(f"\n{len(bad)} requirement(s) not met: {', '.join(bad)}")
        return 1
    print(f"\nall {len(rows)} submission requirements met")
    return 0


if __name__ == "__main__":
    sys.exit(main())
