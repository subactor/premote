from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class QuotaBucket:
    id: str
    name: str
    description: str
    window: str
    remaining_fraction: float
    reset_time: str

    @property
    def remaining_percent(self) -> int:
        return int(round(self.remaining_fraction * 100))


@dataclass(frozen=True)
class QuotaGroup:
    name: str
    description: str
    buckets: tuple[QuotaBucket, ...]


@dataclass(frozen=True)
class QuotaReport:
    groups: tuple[QuotaGroup, ...]
    raw_text: str = ""

    @classmethod
    def from_json_dict(cls, data: dict[str, Any], raw_text: str = "") -> "QuotaReport":
        usage_data = data.get("command", {}).get("data", {})
        raw_groups = usage_data.get("groups", [])
        groups = []
        for g in raw_groups:
            buckets = []
            for b in g.get("buckets", []):
                buckets.append(
                    QuotaBucket(
                        id=str(b.get("id", "")),
                        name=str(b.get("name", "")),
                        description=str(b.get("description", "")),
                        window=str(b.get("window", "")),
                        remaining_fraction=float(b.get("remaining_fraction", 0.0)),
                        reset_time=str(b.get("reset_time", "")),
                    )
                )
            groups.append(
                QuotaGroup(
                    name=str(g.get("name", "")),
                    description=str(g.get("description", "")),
                    buckets=tuple(buckets),
                )
            )
        return cls(groups=tuple(groups), raw_text=raw_text)


@dataclass(frozen=True)
class WindowInfo:
    id: str
    desktop: int
    x: int
    y: int
    width: int
    height: int
    title: str


@dataclass(frozen=True)
class PromptResult:
    response: str
    conversation_id: str = ""
    status: str = "SUCCESS"
    duration_seconds: float = 0.0
    raw_json: dict[str, Any] = field(default_factory=dict)
