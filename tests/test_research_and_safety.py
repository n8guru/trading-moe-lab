from __future__ import annotations

import ast
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_moe_lab.broker import Order
from trading_moe_lab.frozen_specs import h1_mapping
from trading_moe_lab.research import ResearchContext
from trading_moe_lab.research.orchestrator import Budget, Orchestrator
from trading_moe_lab.risk import gate_orders
from trading_moe_lab.spec import spec_from_mapping
from trading_moe_lab.store import Store
from trading_moe_lab.universe import load_universe

from test_engine_invariants import fixtures


class PitTests(unittest.TestCase):
    def test_inception_and_delist(self) -> None:
        uni = load_universe(fixtures() / "universe.json")
        self.assertFalse(uni.is_tradable("NEWZ", date(2020, 12, 31)))
        self.assertTrue(uni.is_tradable("NEWZ", date(2021, 1, 4)))
        self.assertTrue(uni.is_tradable("OLDZ", date(2020, 5, 29)))
        self.assertFalse(uni.is_tradable("OLDZ", date(2020, 6, 1)))
        self.assertFalse(uni.is_tradable("OLDZ", date(2021, 1, 4)))
        self.assertIn("SPY", uni.allowlist())
        self.assertNotIn("OLDZ", uni.allowlist())
        self.assertNotIn("NEWZ", uni.allowlist())

    def test_gate_rejects_untradable(self) -> None:
        uni = load_universe(fixtures() / "universe.json")
        spec = spec_from_mapping(h1_mapping())
        order = Order("oid", "sid", "OLDZ", "BUY", 1)
        accepted, reasons = gate_orders(
            [order],
            spec=spec,
            universe=uni,
            session=date(2019, 6, 3),
            positions={},
            prices={"OLDZ": spec_from_mapping(h1_mapping()).cost.bps_1x and __import__("trading_moe_lab.money", fromlist=["D"]).D("10")},
            nav=__import__("trading_moe_lab.money", fromlist=["D"]).D("1000000"),
            settled_cash=__import__("trading_moe_lab.money", fromlist=["D"]).D("1000000"),
        )
        self.assertEqual(accepted, [])
        self.assertTrue(any("not in spec universe" in r or "not PIT" in r for r in reasons))


class ExpertSandboxTests(unittest.TestCase):
    def test_context_hides_broker(self) -> None:
        from trading_moe_lab.bars import load_barset

        bars = load_barset(fixtures())
        uni = load_universe(fixtures() / "universe.json")
        ctx = ResearchContext(
            bars=bars,
            universe=uni,
            allowlist=uni.allowlist(),
            cycle=0,
            prior_critiques=(),
            prior_proposals=(),
            family_quotas={"H3_REVERSAL": 2},
            family_used={},
        )
        with self.assertRaises(AttributeError):
            _ = ctx.broker  # type: ignore[attr-defined]
        with self.assertRaises(AttributeError):
            _ = ctx.api_key  # type: ignore[attr-defined]

    def test_offline_two_cycles_reject_lookahead_keep_rejected(self) -> None:
        from trading_moe_lab.bars import load_barset

        bars = load_barset(fixtures())
        uni = load_universe(fixtures() / "universe.json")
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "r.sqlite")
            report = Orchestrator(store, Budget(cycles=2, max_trials=16)).run(bars, uni)
            self.assertEqual(report.cycles, 2)
            self.assertGreaterEqual(report.expert_calls, 12)
            titles_rej = {r["title"] for r in report.rejected}
            self.assertTrue(any("look-ahead" in t or "cheat" in t.lower() for t in titles_rej))
            statuses = {t.status for t in store.list_trials()}
            self.assertIn("REJECTED", statuses)
            self.assertTrue(any(t.status == "REGISTERED" for t in store.list_trials()))
            # No champion mutation.
            self.assertIsNone(store.get_champion())
            store.close()

    def test_research_modules_have_no_socket_or_env(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "trading_moe_lab" / "research"
        forbidden = {"socket", "http.client", "urllib.request", "requests", "openai"}
        for path in root.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for n in node.names:
                        self.assertNotIn(n.name.split(".")[0], {f.split(".")[0] for f in forbidden})
                if isinstance(node, ast.ImportFrom) and node.module:
                    self.assertNotIn(node.module.split(".")[0], {"socket", "requests", "openai"})


class NoLiveTests(unittest.TestCase):
    def test_source_has_no_live_broker(self) -> None:
        root = Path(__file__).resolve().parents[1] / "src" / "trading_moe_lab"
        hits = []
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if "class Live" in text or "class Alpaca" in text or "ib_insync" in text:
                hits.append(str(path))
            if "alpaca.trade" in text.lower() or "interactivebrokers" in text.lower():
                hits.append(str(path))
        self.assertEqual(hits, [])

    def test_env_blocks_start(self) -> None:
        from trading_moe_lab.errors import ConfigError
        from trading_moe_lab.safety import assert_paper_only

        os.environ["TRADING_MOE_LIVE"] = "1"
        try:
            with self.assertRaises(ConfigError):
                assert_paper_only()
        finally:
            del os.environ["TRADING_MOE_LIVE"]


if __name__ == "__main__":
    unittest.main()
