"""Research-zone types. No broker, no store writes except via Orchestrator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from trading_moe_lab.bars import BarSet
from trading_moe_lab.spec import ExperimentSpec
from trading_moe_lab.universe import Universe


@dataclass(frozen=True)
class ResearchContext:
    """Read-only view handed to experts. Deliberately has no broker / kill / store."""

    bars: BarSet
    universe: Universe
    allowlist: frozenset[str]
    cycle: int
    prior_critiques: tuple[str, ...]
    prior_proposals: tuple["Proposal", ...]
    family_quotas: dict[str, int]
    family_used: dict[str, int]
    notes: str = ""

    def __getattribute__(self, name: str):
        if name.lower() in {"broker", "kill", "store", "engine", "credentials", "api_key"}:
            raise AttributeError("research context does not expose execution or secrets")
        return object.__getattribute__(self, name)


@dataclass(frozen=True)
class Proposal:
    expert_role: str
    title: str
    family: str
    rationale: str
    spec_draft: dict[str, Any]
    tainted: bool = False
    taint_reason: str = ""
    withdraw: bool = False


@dataclass(frozen=True)
class Critique:
    expert_role: str
    target_title: str
    severity: str  # INFO, WARN, REJECT
    issues: tuple[str, ...]
    accept: bool


class Expert(Protocol):
    role: str

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        ...

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        ...
