"""Typed failures. None of these may be waived by an expert."""


class LabError(Exception):
    """Base error for the lab."""


class ConfigError(LabError):
    """Invalid configuration or forbidden venue."""


class SpecError(LabError):
    """ExperimentSpec failed schema / invariant checks."""


class DataFault(LabError):
    """Bar or universe validation failed. Engine must latch, not trade through."""


class RiskReject(LabError):
    """Pre-trade risk gate rejected an order."""


class KillLatched(LabError):
    """Kill switch is latched; new orders are forbidden."""


class IdempotencyError(LabError):
    """Session replay payload does not match the stored session."""


class HoldoutError(LabError):
    """Holdout window already consumed (one-use)."""


class BudgetError(LabError):
    """Orchestrator budget exhausted."""


class RegistryError(LabError):
    """Trial registry refused a mutation."""
