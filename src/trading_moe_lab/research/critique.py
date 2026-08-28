"""CritiqueExpert — adversarial review: look-ahead, PIT, multiple-testing, universe bias."""

from __future__ import annotations

from trading_moe_lab.research import Critique, Proposal, ResearchContext

LOOKAHEAD_KEYS = {
    "look_ahead_days",
    "lookahead",
    "use_future_returns",
    "future_close",
    "next_month_return",
}


class CritiqueExpert:
    role = "CritiqueExpert"

    def propose(self, ctx: ResearchContext) -> list[Proposal]:
        return []  # critic does not originate specs

    def critique(self, ctx: ResearchContext, proposals: list[Proposal]) -> list[Critique]:
        out: list[Critique] = []
        seen_hashes: set[str] = set()
        for p in proposals:
            issues: list[str] = []
            draft = p.spec_draft
            params = draft.get("params") or {}
            for k, v in params.items():
                if str(k).lower() in LOOKAHEAD_KEYS or v is True and "future" in str(k).lower():
                    issues.append(f"look-ahead knob {k}={v}")
            if p.tainted:
                issues.append(p.taint_reason or "marked tainted by origin expert")
            timing = str(draft.get("signal_timing", "PREV_CLOSE")).upper()
            exec_t = str(draft.get("execution_timing", "NEXT_OPEN")).upper()
            if timing != "PREV_CLOSE":
                issues.append(f"signal_timing {timing} is not PIT")
            if exec_t != "NEXT_OPEN":
                issues.append(f"execution_timing {exec_t} allows same-bar leakage")
            uni = [str(x).upper() for x in draft.get("universe") or []]
            for s in uni:
                if s not in ctx.allowlist:
                    issues.append(f"universe bias / not allowlisted: {s}")
            if draft.get("venue") not in (None, "LOCAL_SIM", "PAPER"):
                issues.append("non-sim venue")
            # Multiple-testing: reject extra H3 beyond quota
            if p.family == "H3_REVERSAL":
                used = ctx.family_used.get("H3_REVERSAL", 0)
                if used >= ctx.family_quotas.get("H3_REVERSAL", 2):
                    issues.append("H3 familywise quota exhausted (multiple-testing budget)")
            # Dedup note
            ident = str(draft.get("spec_id"))
            if ident in seen_hashes:
                issues.append("duplicate spec_id in this cycle")
            seen_hashes.add(ident)

            reject = bool(issues) and (
                p.tainted
                or any("look-ahead" in i or "not PIT" in i or "quota" in i or "allowlisted" in i for i in issues)
            )
            out.append(
                Critique(
                    expert_role=self.role,
                    target_title=p.title,
                    severity="REJECT" if reject else ("WARN" if issues else "INFO"),
                    issues=tuple(issues) if issues else ("no material PIT / look-ahead / universe issues",),
                    accept=not reject,
                )
            )
        return out
