from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_moe_lab.bars import load_barset
from trading_moe_lab.engine import run_engine
from trading_moe_lab.frozen_specs import frozen_specs
from trading_moe_lab.hashes import sha256_text
from trading_moe_lab.store import Store
from trading_moe_lab.synthesize import generate_fixtures
from trading_moe_lab.universe import load_universe

_FIXTURES: Path | None = None


def fixtures() -> Path:
    global _FIXTURES
    if _FIXTURES is None:
        from trading_moe_lab.paths import default_fixtures

        dest = default_fixtures()
        if not (dest / "digests.json").exists():
            generate_fixtures(dest)
        _FIXTURES = dest
    return _FIXTURES


class ReplayTests(unittest.TestCase):
    def test_bit_stable_nav_two_stores(self) -> None:
        fx = fixtures()
        bars = load_barset(fx)
        uni = load_universe(fx / "universe.json")
        spec = frozen_specs()["H1"]
        navs = []
        fills = []
        for i in range(2):
            with tempfile.TemporaryDirectory() as td:
                store = Store(Path(td) / "lab.sqlite")
                result = run_engine(spec, bars, uni, store, run_id=f"replay-{i}", cost_multiple="1x")
                navs.append([(d, v) for d, v in result.nav])
                fills.append(
                    [
                        (f["session"], f["symbol"], f["side"], f["qty"], f["price"], f["fee"], f["remaining_cancelled"])
                        for f in result.fills
                    ]
                )
                store.close()
        self.assertEqual(navs[0], navs[1])
        self.assertEqual(fills[0], fills[1])
        self.assertGreater(len(navs[0]), 16)

    def test_session_idempotent_no_double_fill(self) -> None:
        fx = fixtures()
        bars = load_barset(fx)
        uni = load_universe(fx / "universe.json")
        spec = frozen_specs()["H2"]
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "lab.sqlite"
            store = Store(db)
            r1 = run_engine(spec, bars, uni, store, run_id="idem-1", cost_multiple="1x")
            n_sessions = store._cx.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            r2 = run_engine(spec, bars, uni, store, run_id="idem-1", cost_multiple="1x")
            n_sessions2 = store._cx.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
            self.assertEqual(n_sessions, n_sessions2)
            self.assertEqual(r1.nav, r2.nav)
            store.close()


class KillTests(unittest.TestCase):
    def test_latch_persists_and_blocks_orders(self) -> None:
        fx = fixtures()
        bars = load_barset(fx)
        uni = load_universe(fx / "universe.json")
        raw = frozen_specs()["SPY"].canonical_dict()
        raw["risk"] = dict(raw["risk"])
        raw["risk"]["kill_drawdown"] = "0.08"
        from trading_moe_lab.spec import spec_from_mapping

        spec = spec_from_mapping(raw)
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "lab.sqlite"
            store = Store(db)
            r = run_engine(spec, bars, uni, store, run_id="kill-run", cost_multiple="1x")
            self.assertTrue(r.kill["latched"], msg=r.kill)
            # New engine / kill object on the same run_id sees the latch.
            from trading_moe_lab.kill import KillSwitch

            ks = KillSwitch(store, "kill-run", spec.risk.kill_drawdown)
            self.assertTrue(ks.state.latched)
            self.assertFalse(ks.can_place_orders())
            orders_after = store._cx.execute(
                "SELECT COUNT(*) AS n FROM sessions WHERE run_id=?", ("kill-run",)
            ).fetchone()["n"]
            self.assertGreater(orders_after, 10)
            store.close()


class HoldoutTests(unittest.TestCase):
    def test_one_use(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            store = Store(Path(td) / "lab.sqlite")
            spec = frozen_specs()["H1"]
            store.consume_holdout(spec.family, spec.holdout_window.start, spec.holdout_window.end, "t1")
            from trading_moe_lab.errors import HoldoutError

            with self.assertRaises(HoldoutError):
                store.consume_holdout(spec.family, spec.holdout_window.start, spec.holdout_window.end, "t2")
            # Different family still allowed.
            store.consume_holdout("H2_CS_MOMENTUM", spec.holdout_window.start, spec.holdout_window.end, "t3")
            store.close()


class SettlementTests(unittest.TestCase):
    def test_t1_not_same_day(self) -> None:
        from datetime import date

        from trading_moe_lab.settlement import CashBook

        book = CashBook(settled=__import__("trading_moe_lab.money", fromlist=["D"]).D("100"))
        book.credit_t1("40", date(2018, 1, 3))
        self.assertEqual(str(book.settled), "100.00000000")
        book.settle(date(2018, 1, 2))
        self.assertEqual(str(book.settled), "100.00000000")
        book.settle(date(2018, 1, 3))
        self.assertEqual(str(book.settled), "140.00000000")


if __name__ == "__main__":
    unittest.main()
