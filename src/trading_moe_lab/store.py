"""SQLite WAL store: trials, sessions, kill latch, holdout leases, audit chain."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from trading_moe_lab.errors import HoldoutError, IdempotencyError, RegistryError
from trading_moe_lab.hashes import canonical_json, sha256_text

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trials (
  trial_id TEXT PRIMARY KEY,
  spec_hash TEXT NOT NULL,
  spec_json TEXT NOT NULL,
  family TEXT NOT NULL,
  status TEXT NOT NULL,
  split TEXT NOT NULL,
  metrics_json TEXT,
  created_ts TEXT NOT NULL,
  notes TEXT,
  source TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS holdout_leases (
  family TEXT NOT NULL,
  holdout_start TEXT NOT NULL,
  holdout_end TEXT NOT NULL,
  trial_id TEXT NOT NULL,
  created_ts TEXT NOT NULL,
  PRIMARY KEY (family, holdout_start, holdout_end)
);

CREATE TABLE IF NOT EXISTS kill_switch (
  run_id TEXT PRIMARY KEY,
  latched INTEGER NOT NULL,
  reason TEXT,
  latched_on TEXT,
  peak_nav TEXT,
  nav TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  session_date TEXT NOT NULL,
  payload_hash TEXT NOT NULL,
  result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  run_id TEXT,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  entry_hash TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nav_series (
  run_id TEXT NOT NULL,
  session_date TEXT NOT NULL,
  nav TEXT NOT NULL,
  cash TEXT NOT NULL,
  gross_exposure TEXT NOT NULL,
  PRIMARY KEY (run_id, session_date)
);

CREATE TABLE IF NOT EXISTS champion (
  slot TEXT PRIMARY KEY,
  spec_hash TEXT NOT NULL,
  trial_id TEXT NOT NULL,
  set_ts TEXT NOT NULL
);
"""

TERMINAL_STATUSES = frozenset({"ACCEPTED", "REJECTED", "INCONCLUSIVE", "FAILED", "REGISTERED"})


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class TrialRow:
    trial_id: str
    spec_hash: str
    spec_json: str
    family: str
    status: str
    split: str
    metrics_json: str | None
    created_ts: str
    notes: str | None
    source: str


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._cx = sqlite3.connect(str(self.path), isolation_level=None)
        self._cx.row_factory = sqlite3.Row
        self._cx.execute("PRAGMA journal_mode=WAL;")
        self._cx.execute("PRAGMA foreign_keys=ON;")
        self._cx.executescript(SCHEMA)
        self._ensure_genesis()

    def close(self) -> None:
        self._cx.close()

    def _ensure_genesis(self) -> None:
        row = self._cx.execute("SELECT v FROM meta WHERE k='audit_tip'").fetchone()
        if row is None:
            self._cx.execute(
                "INSERT INTO meta(k, v) VALUES ('audit_tip', ?), ('float_policy_id', 'decimal-v0-8dp-half-even')",
                ("GENESIS",),
            )

    def audit(self, kind: str, payload: dict[str, Any], run_id: str | None = None) -> str:
        prev = self._cx.execute("SELECT v FROM meta WHERE k='audit_tip'").fetchone()["v"]
        body = canonical_json({"kind": kind, "payload": payload, "run_id": run_id, "prev": prev})
        entry_hash = sha256_text(body)
        self._cx.execute(
            "INSERT INTO audit_log(ts, run_id, kind, payload_json, prev_hash, entry_hash) VALUES (?,?,?,?,?,?)",
            (_utcnow(), run_id, kind, canonical_json(payload), prev, entry_hash),
        )
        self._cx.execute("UPDATE meta SET v=? WHERE k='audit_tip'", (entry_hash,))
        return entry_hash

    def audit_tip(self) -> str:
        return self._cx.execute("SELECT v FROM meta WHERE k='audit_tip'").fetchone()["v"]

    # --- kill ---
    def get_kill(self, run_id: str) -> dict[str, Any] | None:
        row = self._cx.execute("SELECT * FROM kill_switch WHERE run_id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def set_kill(self, run_id: str, latched: bool, reason: str | None, latched_on: str | None, peak_nav: str, nav: str) -> None:
        self._cx.execute(
            """INSERT INTO kill_switch(run_id, latched, reason, latched_on, peak_nav, nav)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(run_id) DO UPDATE SET
                 latched=excluded.latched, reason=excluded.reason, latched_on=excluded.latched_on,
                 peak_nav=excluded.peak_nav, nav=excluded.nav""",
            (run_id, 1 if latched else 0, reason, latched_on, peak_nav, nav),
        )
        if latched:
            self.audit("KILL_LATCH", {"run_id": run_id, "reason": reason, "nav": nav, "peak_nav": peak_nav}, run_id)

    # --- sessions ---
    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._cx.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        return dict(row) if row else None

    def put_session(self, session_id: str, run_id: str, session_date: str, payload_hash: str, result: dict[str, Any]) -> None:
        existing = self.get_session(session_id)
        if existing:
            if existing["payload_hash"] != payload_hash:
                raise IdempotencyError(
                    f"session {session_id} exists with different payload hash"
                )
            return
        self._cx.execute(
            "INSERT INTO sessions(session_id, run_id, session_date, payload_hash, result_json) VALUES (?,?,?,?,?)",
            (session_id, run_id, session_date, payload_hash, canonical_json(result)),
        )

    # --- NAV ---
    def put_nav(self, run_id: str, session_date: str, nav: str, cash: str, gross: str) -> None:
        self._cx.execute(
            """INSERT INTO nav_series(run_id, session_date, nav, cash, gross_exposure)
               VALUES (?,?,?,?,?)
               ON CONFLICT(run_id, session_date) DO UPDATE SET
                 nav=excluded.nav, cash=excluded.cash, gross_exposure=excluded.gross_exposure""",
            (run_id, session_date, nav, cash, gross),
        )

    def nav_series(self, run_id: str) -> list[tuple[str, str]]:
        rows = self._cx.execute(
            "SELECT session_date, nav FROM nav_series WHERE run_id=? ORDER BY session_date",
            (run_id,),
        ).fetchall()
        return [(r["session_date"], r["nav"]) for r in rows]

    # --- trials / holdout ---
    def register_trial(
        self,
        trial_id: str,
        spec_hash: str,
        spec_json: str,
        family: str,
        status: str,
        split: str,
        source: str,
        notes: str = "",
        metrics: dict | None = None,
    ) -> None:
        existing = self._cx.execute("SELECT trial_id FROM trials WHERE trial_id=?", (trial_id,)).fetchone()
        if existing:
            raise RegistryError(f"trial_id already exists: {trial_id}")
        self._cx.execute(
            """INSERT INTO trials(trial_id, spec_hash, spec_json, family, status, split, metrics_json, created_ts, notes, source)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                trial_id,
                spec_hash,
                spec_json,
                family,
                status,
                split,
                canonical_json(metrics) if metrics is not None else None,
                _utcnow(),
                notes,
                source,
            ),
        )
        self.audit(
            "TRIAL_REGISTER",
            {"trial_id": trial_id, "family": family, "status": status, "spec_hash": spec_hash, "split": split},
        )

    def update_trial(self, trial_id: str, status: str, metrics: dict | None = None, notes: str | None = None) -> None:
        row = self._cx.execute("SELECT * FROM trials WHERE trial_id=?", (trial_id,)).fetchone()
        if row is None:
            raise RegistryError(f"unknown trial {trial_id}")
        self._cx.execute(
            "UPDATE trials SET status=?, metrics_json=?, notes=COALESCE(?, notes) WHERE trial_id=?",
            (status, canonical_json(metrics) if metrics is not None else row["metrics_json"], notes, trial_id),
        )
        self.audit("TRIAL_UPDATE", {"trial_id": trial_id, "status": status}, None)

    def list_trials(self) -> list[TrialRow]:
        rows = self._cx.execute("SELECT * FROM trials ORDER BY created_ts, trial_id").fetchall()
        return [
            TrialRow(
                trial_id=r["trial_id"],
                spec_hash=r["spec_hash"],
                spec_json=r["spec_json"],
                family=r["family"],
                status=r["status"],
                split=r["split"],
                metrics_json=r["metrics_json"],
                created_ts=r["created_ts"],
                notes=r["notes"],
                source=r["source"],
            )
            for r in rows
        ]

    def family_trial_count(self, family: str) -> int:
        row = self._cx.execute("SELECT COUNT(*) AS n FROM trials WHERE family=?", (family,)).fetchone()
        return int(row["n"])

    def consume_holdout(self, family: str, holdout_start: str, holdout_end: str, trial_id: str) -> None:
        existing = self._cx.execute(
            "SELECT trial_id FROM holdout_leases WHERE family=? AND holdout_start=? AND holdout_end=?",
            (family, holdout_start, holdout_end),
        ).fetchone()
        if existing:
            raise HoldoutError(
                f"holdout already used for family {family} by trial {existing['trial_id']}"
            )
        self._cx.execute(
            "INSERT INTO holdout_leases(family, holdout_start, holdout_end, trial_id, created_ts) VALUES (?,?,?,?,?)",
            (family, holdout_start, holdout_end, trial_id, _utcnow()),
        )
        self.audit(
            "HOLDOUT_CONSUME",
            {"family": family, "start": holdout_start, "end": holdout_end, "trial_id": trial_id},
        )

    def holdout_used(self, family: str, holdout_start: str, holdout_end: str) -> bool:
        row = self._cx.execute(
            "SELECT 1 FROM holdout_leases WHERE family=? AND holdout_start=? AND holdout_end=?",
            (family, holdout_start, holdout_end),
        ).fetchone()
        return row is not None

    def set_champion(self, spec_hash: str, trial_id: str, slot: str = "default") -> None:
        trial = self._cx.execute("SELECT * FROM trials WHERE trial_id=?", (trial_id,)).fetchone()
        if trial is None:
            raise RegistryError("champion trial does not exist")
        if trial["status"] != "ACCEPTED":
            raise RegistryError("champion must reference an ACCEPTED trial (experts cannot set this)")
        if trial["spec_hash"] != spec_hash:
            raise RegistryError("champion spec_hash mismatch")
        self._cx.execute(
            """INSERT INTO champion(slot, spec_hash, trial_id, set_ts) VALUES (?,?,?,?)
               ON CONFLICT(slot) DO UPDATE SET spec_hash=excluded.spec_hash, trial_id=excluded.trial_id, set_ts=excluded.set_ts""",
            (slot, spec_hash, trial_id, _utcnow()),
        )
        self.audit("CHAMPION_SET", {"slot": slot, "spec_hash": spec_hash, "trial_id": trial_id})

    def get_champion(self, slot: str = "default") -> dict[str, Any] | None:
        row = self._cx.execute("SELECT * FROM champion WHERE slot=?", (slot,)).fetchone()
        return dict(row) if row else None

    def dump_registry(self) -> dict[str, Any]:
        trials = [r.__dict__ for r in self.list_trials()]
        leases = [dict(r) for r in self._cx.execute("SELECT * FROM holdout_leases").fetchall()]
        return {
            "audit_tip": self.audit_tip(),
            "trials": trials,
            "holdout_leases": leases,
            "champion": self.get_champion(),
        }
