"""SpecScribeExpert — accepted ideas become typed immutable ExperimentSpec JSON."""

from __future__ import annotations

from trading_moe_lab.errors import SpecError
from trading_moe_lab.research import Critique, Proposal, ResearchContext
from trading_moe_lab.spec import ExperimentSpec, spec_from_mapping


class SpecScribeExpert:
    role = "SpecScribeExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        return []

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        return []

    def scribe(self, proposal: Proposal) -> ExperimentSpec:
        try:
            return spec_from_mapping(proposal.spec_draft)
        except SpecError as exc:
            raise SpecError(f"{proposal.title}: {exc}") from exc
