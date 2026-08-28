"""LLM adapter interface. Default is offline heuristic (no network, no keys)."""

from __future__ import annotations

from typing import Protocol


class LLMAdapter(Protocol):
    name: str

    def complete(self, prompt: str) -> str:
        """Return a completion. Must not place orders or touch credentials."""
        ...


class OfflineHeuristicAdapter:
    """Stand-in used by v0 experts. Deterministic, zero network."""

    name = "offline-heuristic-v0"

    def complete(self, prompt: str) -> str:
        # Experts do not actually need a completion; they run local rules.
        # Returning a stub keeps the interface honest for a future file-replay adapter.
        return f"[offline] {len(prompt)} chars; no model invoked"


class ForbiddenLiveAdapter:
    """Exists only so tests can prove we refuse network/live completions."""

    name = "forbidden"

    def complete(self, prompt: str) -> str:
        raise RuntimeError("live/network LLM adapters are not shipped in v0")
