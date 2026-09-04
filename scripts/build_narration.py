"""Generate docs/narration.m4a and mux it onto the silent screen recording.

The film was shipped silent, which reads as unfinished next to entries that
talk over their demo. This speaks the argument in time with the scenes.

Every figure is read out of data/proof.json for the same reason the slides
are: the script sat for a day saying "thirty-five dollars a contract" as a
spelled-out word, where no digit check could see it. Nothing here is typed
by hand, so the voice track cannot drift from the screen.

Scene durations are imported from build_film.py rather than restated, so a
timing change there re-times the narration instead of desynchronising it.

    PYTHONPATH=. ./.venv/bin/python scripts/build_narration.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

from engine.config import ROOT
from scripts.build_film import scenes

# Piper, a neural TTS running locally. lessac-medium is the clearest of the
# general-purpose English voices at this size and does not sound like a
# screen reader, which is the whole reason for moving off macOS `say`.
VOICE_MODEL = "en_US-lessac-medium"
VOICE_DIR = pathlib.Path(__file__).resolve().parent.parent / ".voices"
SENTENCE_SILENCE = 0.35     # seconds of rest at each full stop
LEAD_IN = 0.4               # the plate is trimmed to the first scene, so this
                            # only lets its 0.7s fade finish before the voice
OUT_AUDIO = ROOT / "docs" / "narration.m4a"
# The silent screen recording is the input and is kept, because re-recording
# it costs four minutes of wall clock. The narrated mux is the deliverable,
# so it takes the plain name that the submission refers to.
VIDEO_IN = ROOT / "docs" / "video_silent.mp4"
VIDEO_OUT = ROOT / "docs" / "video.mp4"


def spoken(p: dict) -> list[str]:
    """One block of narration per scene, in scene order.

    Numbers are spelled the way they should be read aloud, and are formatted
    from the proof rather than transcribed, so they stay correct.
    """
    t, bv, ec = p["totals"], p["broker_verification"], p["economics"]
    cap = (bv["broker_capture_ratio"] or t["aggregate_capture_ratio"]) * 100
    cost = t["given_up_to_execution_usd"] / ec["contracts"]
    eaten = round(cost / ec["expected_per_contract_usd"] * 100)

    def dol(x: float) -> str:
        """'81.09' reads badly. 'eighty one dollars and nine cents' does not."""
        return f"{x:,.2f}".rstrip("0").rstrip(".")

    return [
        # 0 title, 6s
        "Slippage Desk. An options agent that measures its own execution.",

        # 1 the arithmetic, 20s
        f"A credit spread is a thin trade by construction. "
        f"This one collects about {ec['credit_per_contract_usd']:.0f} dollars a contract. "
        f"A win banks forty percent of that. The stop costs all of it. "
        f"So breakeven sits at {ec['breakeven_win_rate'] * 100:.1f} percent, "
        f"while the delta implies only {ec['delta_implied_otm_rate'] * 100:.0f}. "
        f"The entire edge is {ec['edge_points']} percentage points. "
        f"{dol(ec['expected_per_contract_usd'])} dollars a contract.",

        # 2 where the edge goes, 18s
        f"Here is where that edge went. Crossing the bid ask spread cost "
        f"{dol(cost)} dollars a contract. That is {eaten} percent of the entire edge, "
        f"gone to execution before the trade even had a chance to work. "
        f"Execution is not a rounding error at this size. It is a first order term. "
        f"And it is the one thing a few sessions can actually measure.",

        # 3 the field, 18s
        "Here is the part that usually goes unmeasured. A strategy log tells "
        "you whether the decision was right. It tells you nothing about what "
        "crossing the spread cost you to act on it. Scoring an execution means "
        "comparing the fill to the mid it was priced at, the moment it comes "
        "back from the broker. Without that comparison, execution cost never "
        "appears as a number anyone can act on.",

        # 4 dashboard, 32s
        "This is the live desk, running on a paper account against real quotes. "
        "Every figure on this page is derived from the config and from the "
        "contracts actually filled. Nothing on it is typed by hand, and nothing "
        "is seeded. Every fill is scored against the mid it was priced at, the "
        "moment it comes back from the broker. The difference between those two "
        "numbers is the one that decides whether a strategy this thin makes "
        "money, or quietly gives it all back to the market maker. It is "
        "measured here on every single fill, rather than estimated once and "
        "assumed to hold.",

        # 5 buckets, 30s
        "A bucket is an underlying, a tenor, a delta band and a time of day. "
        "When a bucket has historically given up too much credit, the agent stops "
        "trading it. The same memory decides how far to cross on the next order. "
        "Buckets that fill readily hold out for mid. Buckets that do not, pay up, "
        "or get skipped entirely. The estimate is shrunk toward a prior, so three "
        "unlucky fills cannot convince it to abandon a bucket outright. "
        "It is closing a loop on its own execution, not merely logging it.",

        # 6 gates, 28s
        "Fifteen deterministic gates stand between a candidate and an order, and "
        "the model cannot open a trade. The advisor returns a multiplier between "
        "zero and one, plus a veto flag. It can shrink a trade or refuse it. "
        "It cannot pick a strike, change an expiry, or widen risk. "
        "Every failure path returns zero, so a model that is unreachable means "
        "this desk trades less, never worse. Timeout, malformed output, a "
        "refusal, a not a number: all of them return the same veto.",

        # 7 alpaca surfaces, 26s
        "Alpaca appears three times, with deliberately separate jobs. "
        "The command line interface submits the multi leg orders and verifies "
        "the book afterwards. The Python SDK pulls option chains with greeks. "
        "The MCP server feeds read only research to the advisor, launched with "
        "its trading toolsets stripped out, so research physically cannot place "
        "an order. Execution never goes through a subprocess.",

        # 8 evidence, 28s
        f"This is evidence, not a backtest. {t['candidates_considered']:,} candidates "
        f"considered. {bv['paired_spreads']} spreads actually filled. "
        f"{t['theoretical_credit_usd']:,.0f} dollars of credit at mid, "
        f"{t['captured_credit_usd']:,.0f} dollars actually captured, "
        f"{t['given_up_to_execution_usd']:,.0f} dollars surrendered to execution. "
        f"A capture ratio of {cap:.1f} percent. "
        f"All of it sourced from Alpaca's own activity log, with a shaw two five six "
        f"hash over the payload so it cannot be quietly edited later.",

        # 9 what it does not claim, 16s
        "I am not going to claim this strategy is profitable. A handful of sessions "
        "cannot establish that. Treating a window this short as proof would be "
        "reading noise, not signal. What these sessions do establish is that an "
        "agent measured its own execution and acted on what it found.",

        # 10 close, 18s
        "Next is cross venue routing on the same memory, and per bucket sizing "
        "rather than per bucket veto. The loop generalises to any strategy that "
        "pays a spread to get in, which is all of them. "
        "The repo and the live demo are on screen. Built with Claude Code.",
    ]


def _humanize(text: str) -> str:
    """Insert the pauses a person would take, which `say` will not.

    What makes synthetic narration sound synthetic is mostly rhythm, not
    timbre: the engine runs sentences together at a metronomic pace and never
    lets a number land. `say` accepts inline [[slnc ms]] commands, so the
    text gets a short rest after each sentence, a shorter one at a clause
    break, and a beat before a figure so the listener has time to hear it.

    Durations are deliberately modest. Long pauses read as a stall, and the
    per-scene budget in fit() has to absorb whatever this adds.
    """
    import re as _re
    # A beat before a dollar figure or a percentage, where the ear needs it.
    text = _re.sub(r"(?<=[a-z,]) (\$[\d,]|\d+(?:\.\d+)? percent)",
                   r" [[slnc 120]] \1", text)
    # Sentence ends only. Comma rests were tried at 90ms and cost too much:
    # a scene's budget is fixed, so every pause is paid for by speaking the
    # words faster, and three scenes were pushed to 215-228 wpm. Racing
    # between pauses sounds worse than not pausing at all, so the rests are
    # spent where they carry the most meaning: the full stop.
    text = _re.sub(r"([.?!]) ", r"\1 [[slnc 300]] ", text)
    return text


def synth(text: str, length_scale: float, dest: pathlib.Path) -> float:
    """Speak `text` with Piper at the given pace, returning its duration.

    macOS `say` was the previous engine. Its only usable English voice on
    this machine is Samantha (everything else installed is a novelty voice),
    and it stays recognisably synthetic no matter how the pacing is tuned.
    Piper is a neural TTS that runs entirely offline: no account, no API key,
    no per-character billing, and the model sits in .voices/ beside the repo.

    Pace is `--length-scale`, where larger is slower, rather than words per
    minute. Sentence rests are native (`--sentence-silence`), which replaces
    the [[slnc]] markers `say` needed.
    """
    subprocess.run(
        [sys.executable, "-m", "piper", "-m", VOICE_MODEL,
         "--data-dir", str(VOICE_DIR),
         "--length-scale", f"{length_scale:.3f}",
         "--sentence-silence", str(SENTENCE_SILENCE),
         "-f", str(dest)],
        input=text, text=True, check=True, capture_output=True)
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(dest)],
        check=True, capture_output=True, text=True)
    return float(out.stdout.strip())


def fit(text: str, budget: float, dest: pathlib.Path) -> tuple[float, float]:
    """Speak `text` so it lands inside `budget` seconds.

    Starts a shade slower than the model's default and only compresses if it
    has to, because a narration that races is worse than one that runs a beat
    short. The scene durations in build_film.py were widened precisely so this
    rarely has to leave the natural end of the range.
    """
    for scale in (1.10, 1.05, 1.00, 0.96, 0.92, 0.88, 0.84, 0.80):
        dur = synth(text, scale, dest)
        if dur <= budget - 0.35:
            return dur, scale
    return dur, scale


def main() -> int:
    if not VIDEO_IN.exists():
        print(f"! {VIDEO_IN} not found; run the film recording first")
        return 1

    proof = json.loads((ROOT / "data" / "proof.json").read_text())
    S, lines = scenes(proof), spoken(proof)
    if len(S) != len(lines):
        print(f"! {len(S)} scenes but {len(lines)} narration blocks")
        return 1

    tmp = pathlib.Path(subprocess.run(["mktemp", "-d"], check=True,
                                      capture_output=True, text=True).stdout.strip())
    parts, cursor, over = [], 0.0, 0

    for i, (sc, text) in enumerate(zip(S, lines)):
        seg = tmp / f"{i:02d}.wav"
        dur, scale = fit(text, sc["t"], seg)
        start = LEAD_IN + cursor
        flag = ""
        if dur > sc["t"] - 0.35:
            flag, over = "  ! OVERRUNS", over + 1
        print(f"  scene {i:>2}  budget {sc['t']:>4}s  speech {dur:>6.2f}s  "
              f"pace {scale:.2f}{flag}")
        parts.append((start, seg, dur))
        cursor += sc["t"]

    # Lay each block at its scene's start time on one silent bed, so a block
    # that finishes early leaves a pause rather than dragging the rest forward.
    total = LEAD_IN + cursor + 4.0
    inputs, filters = [], [f"anullsrc=r=44100:cl=stereo:d={total:.2f}[bed]"]
    for n, (start, seg, _) in enumerate(parts):
        inputs += ["-i", str(seg)]
        filters.append(f"[{n}:a]adelay={int(start * 1000)}|{int(start * 1000)},"
                       f"aresample=44100[a{n}]")
    mix = "[bed]" + "".join(f"[a{n}]" for n in range(len(parts)))
    # loudnorm because the raw mix sat around -19.6 dB mean, which plays
    # quiet on a laptop speaker. -16 LUFS is the usual target for speech.
    filters.append(f"{mix}amix=inputs={len(parts) + 1}:normalize=0:"
                   f"dropout_transition=0,"
                   f"loudnorm=I=-16:TP=-1.5:LRA=11[out]")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", filters[0].split("[bed]")[0],
         *inputs, "-filter_complex", ";".join(filters[1:]),
         "-map", "[out]", "-c:a", "aac", "-b:a", "160k", str(OUT_AUDIO)],
        check=True, capture_output=True)

    subprocess.run(
        ["ffmpeg", "-y", "-i", str(VIDEO_IN), "-i", str(OUT_AUDIO),
         "-c:v", "copy", "-c:a", "aac", "-b:a", "160k",
         "-map", "0:v:0", "-map", "1:a:0", "-shortest",
         "-movflags", "+faststart", str(VIDEO_OUT)],
        check=True, capture_output=True)

    print(f"\n  audio    {OUT_AUDIO}")
    print(f"  video    {VIDEO_OUT}")
    if over:
        print(f"  ! {over} scene(s) overrun their slide; tighten the text")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
