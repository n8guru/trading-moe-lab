"""MomentumExpert — absolute/relative momentum families (Antonacci-style method)."""

from __future__ import annotations

from trading_moe_lab.frozen_specs import h1_mapping, h2_mapping
from trading_moe_lab.research import Critique, Proposal, ResearchContext


class MomentumExpert:
    role = "MomentumExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        out = [
            Proposal(
                expert_role=self.role,
                title="H1 dual momentum frozen",
                family="H1_DUAL_MOMENTUM",
                rationale=(
                    "Relative momentum between SPY and EFA plus absolute momentum vs BIL. "
                    "Crash sleeve is TLT if its 12m beats bills. Method follows Antonacci GEM "
                    "as a recipe, not as evidence that the edge exists on these fixtures."
                ),
                spec_draft=h1_mapping(),
            ),
            Proposal(
                expert_role=self.role,
                title="H2 cross-sectional momentum frozen",
                family="H2_CS_MOMENTUM",
                rationale="Top-2 12-month TR among a liquid ETF sleeve, absolute filter vs BIL.",
                spec_draft=h2_mapping(),
            ),
        ]
        if ctx.cycle == 0:
            # Negative example: look-ahead draft that CritiqueExpert must REJECT.
            tainted = h1_mapping()
            tainted = dict(tainted)
            tainted["spec_id"] = "h1-lookahead-CHEAT-rejected"
            tainted["params"] = {"look_ahead_days": 21, "use_future_returns": True}
            tainted["notes"] = "INTENTIONALLY TAINTED look-ahead proposal for critique demo."
            out.append(
                Proposal(
                    expert_role=self.role,
                    title="H1 look-ahead cheat (must reject)",
                    family="H1_DUAL_MOMENTUM",
                    rationale="Uses next-month returns. Should never reach the engine.",
                    spec_draft=tainted,
                    tainted=True,
                    taint_reason="look-ahead / future returns in params",
                )
            )
        if ctx.cycle >= 1:
            # Second cycle: 6-month lookback variant, still honest.
            variant = dict(h1_mapping())
            variant["spec_id"] = "h1-dual-momentum-126d-v0"
            variant["lookback_days"] = 126
            variant["name"] = "H1 dual momentum 6-month lookback variant"
            out.append(
                Proposal(
                    expert_role=self.role,
                    title="H1 126d lookback variant",
                    family="H1_DUAL_MOMENTUM",
                    rationale="Cycle-2 honest variant after critique: shorter lookback, still PIT.",
                    spec_draft=variant,
                )
            )
        return out

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        return []
