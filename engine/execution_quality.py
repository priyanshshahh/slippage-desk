"""Execution-quality memory: the agent grades its own fills and stops
trading where it has historically been filled badly.

The premise is that on a short-dated credit spread, edge is measured in
cents and slippage is measured in cents, so where you get filled matters
as much as what you pick. A spread that looks good at mid is not good if
this agent, at this time of day, in this delta bucket, has historically
surrendered a third of the theoretical credit getting in.

So every fill is scored, bucketed, and fed back as a gate. Two numbers
are tracked per bucket:

  capture ratio  actual credit received / theoretical mid credit
                 1.0 means filled at mid, 0.0 means no credit at all
  fill rate      orders that filled / orders submitted

Capture drives a veto. Fill rate drives how aggressively the next order
in that bucket is priced. Both use shrinkage toward a global prior so a
single unlucky fill cannot blacklist a bucket.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from engine.config import ROOT

STORE = ROOT / "data" / "execution_quality.json"

# Shrinkage strength. With k=2, a bucket needs a few observations before
# its own mean outweighs the global prior. This is what stops one bad fill
# from taking a bucket offline.
PRIOR_STRENGTH = 2.0

# Assume mid-ish fills until proven otherwise, so a cold start explores.
PRIOR_CAPTURE = 0.85
PRIOR_FILL_RATE = 0.75


def delta_bucket(abs_delta: float) -> str:
    return f"d{round(abs_delta * 20) / 20:.2f}"


def tod_bucket(now: datetime) -> str:
    """Time of day matters: the open and the close are different markets."""
    minutes = now.hour * 60 + now.minute
    if minutes < 10 * 60 + 30:
        return "open"
    if minutes >= 14 * 60 + 30:
        return "close"
    return "midday"


def bucket_key(underlying: str, dte: int, abs_delta: float, now: datetime) -> str:
    return f"{underlying}:dte{dte}:{delta_bucket(abs_delta)}:{tod_bucket(now)}"


@dataclass
class BucketStats:
    submitted: int = 0
    filled: int = 0
    captures: list[float] = field(default_factory=list)

    @property
    def raw_capture(self) -> float | None:
        return sum(self.captures) / len(self.captures) if self.captures else None

    @property
    def shrunk_capture(self) -> float:
        """Bucket mean pulled toward the global prior by PRIOR_STRENGTH."""
        n = len(self.captures)
        if n == 0:
            return PRIOR_CAPTURE
        total = sum(self.captures) + PRIOR_CAPTURE * PRIOR_STRENGTH
        return total / (n + PRIOR_STRENGTH)

    @property
    def shrunk_fill_rate(self) -> float:
        if self.submitted == 0:
            return PRIOR_FILL_RATE
        total = self.filled + PRIOR_FILL_RATE * PRIOR_STRENGTH
        return total / (self.submitted + PRIOR_STRENGTH)


class ExecutionMemory:
    """Persistent, append-friendly store of per-bucket execution quality."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or STORE
        self.buckets: dict[str, BucketStats] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        raw = json.loads(self.path.read_text())
        self.buckets = {k: BucketStats(**v) for k, v in raw.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps({k: asdict(v) for k, v in self.buckets.items()}, indent=2)
        )

    def _get(self, key: str) -> BucketStats:
        return self.buckets.setdefault(key, BucketStats())

    def record_submission(self, key: str) -> None:
        self._get(key).submitted += 1
        self.save()

    def record_fill(self, key: str, mid_credit: float, actual_credit: float) -> float:
        """Score one fill. Returns the capture ratio."""
        b = self._get(key)
        b.filled += 1
        capture = (actual_credit / mid_credit) if mid_credit > 0 else 0.0
        # Clamp: a better-than-mid fill is luck, not a reason to trust the
        # bucket more than mid.
        capture = max(0.0, min(1.2, capture))
        b.captures.append(round(capture, 4))
        self.save()
        return capture

    def capture(self, key: str) -> float:
        return self._get(key).shrunk_capture

    def fill_rate(self, key: str) -> float:
        return self._get(key).shrunk_fill_rate

    def samples(self, key: str) -> int:
        return len(self._get(key).captures)

    def aggressiveness(self, key: str) -> float:
        """How far to cross the spread on the next order in this bucket.

        0.0 rests at mid, 1.0 crosses fully. If this bucket rarely fills we
        lean toward crossing; if it fills readily we hold out for mid.
        """
        fr = self.fill_rate(key)
        # Low fill rate -> more aggressive. Bounded so we never fully cross.
        return round(max(0.2, min(0.8, 1.0 - fr)), 3)

    def report(self) -> list[dict]:
        rows = []
        for key, b in sorted(self.buckets.items()):
            rows.append(
                {
                    "bucket": key,
                    "submitted": b.submitted,
                    "filled": b.filled,
                    "samples": len(b.captures),
                    "raw_capture": round(b.raw_capture, 4) if b.raw_capture is not None else None,
                    "shrunk_capture": round(b.shrunk_capture, 4),
                    "fill_rate": round(b.shrunk_fill_rate, 4),
                    "aggressiveness": self.aggressiveness(key),
                }
            )
        return rows
