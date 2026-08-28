"""ReversalExpert — short-horizon reversal with tiny trial quota."""

from __future__ import annotations

from trading_moe_lab.frozen_specs import h3_mapping
from trading_moe_lab.research import Critique, Proposal, ResearchContext


class ReversalExpert:
    role = "ReversalExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        used = ctx.family_used.get("H3_REVERSAL", 0)
        quota = ctx.family_quotas.get("H3_REVERSAL", 2)
        remaining = max(0, quota - used)
        if remaining <= 0:
            return [
                Proposal(
                    expert_role=self.role,
                    title="H3 quota exhausted",
                    family="H3_REVERSAL",
                    rationale="Tiny familywise budget already consumed.",
                    spec_draft=h3_mapping(),
                    withdraw=True,
                )
            ]
        drafts = [
            Proposal(
                expert_role=self.role,
                title="H3 5-day reversal frozen",
                family="H3_REVERSAL",
                rationale=(
                    "2–5 day losers tend to bounce in some equity samples; on liquid ETFs with "
                    "10–20 bps costs this is expected to wash out. Pre-register INCONCLUSIVE."
                ),
                spec_draft=h3_mapping(),
            )
        ]
        if ctx.cycle >= 1 and remaining > 1:
            m = dict(h3_mapping())
            m["spec_id"] = "h3-reversal-2d-v0"
            m["lookback_days"] = 2
            m["rebalance_n_days"] = 2
            m["name"] = "H3 2-day reversal (still tiny quota)"
            drafts.append(
                Proposal(
                    expert_role=self.role,
                    title="H3 2-day reversal variant",
                    family="H3_REVERSAL",
                    rationale="Cycle-2 even higher turnover; even more likely to fail after costs.",
                    spec_draft=m,
                )
            )
        return drafts[:remaining]

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        return []
