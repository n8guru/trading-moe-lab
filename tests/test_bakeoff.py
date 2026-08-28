from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_moe_lab.bakeoff import run_bakeoff
from trading_moe_lab.bars import load_barset
from trading_moe_lab.hashes import sha256_file
from trading_moe_lab.synthesize import generate_fixtures

from test_engine_invariants import fixtures


class DigestTests(unittest.TestCase):
    def test_loader_verifies(self) -> None:
        fx = fixtures()
        bars = load_barset(fx, verify_digests=True)
        self.assertIn("SPY", bars.by_symbol)
        self.assertGreater(len(bars.by_symbol["SPY"]), 1000)
        # OLDZ shorter due to delist
        self.assertLess(len(bars.by_symbol["OLDZ"]), len(bars.by_symbol["SPY"]))
        self.assertLess(len(bars.by_symbol["NEWZ"]), len(bars.by_symbol["SPY"]))

    def test_tamper_detected(self) -> None:
        import shutil

        from trading_moe_lab.errors import DataFault

        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "v0"
            shutil.copytree(fixtures(), dest)
            spy = dest / "bars" / "SPY.csv"
            spy.write_text(spy.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(DataFault):
                load_barset(dest, verify_digests=True)


class BakeoffTests(unittest.TestCase):
    def test_bakeoff_emits_summary(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "results"
            summary = run_bakeoff(fixtures_dir=fixtures(), out_dir=out)
            self.assertEqual(summary["venue"], "LOCAL_SIM")
            self.assertIn("H1_1x", summary["runs"])
            self.assertIn("H3_2x", summary["runs"])
            self.assertIn("SPY_1x", summary["runs"])
            self.assertEqual(summary["outcomes"]["H3"], "INCONCLUSIVE")
            self.assertTrue((out / "summary.json").exists())
            self.assertTrue((out / "equity_curve.png").exists())
            self.assertTrue((out / "equity_curve.svg").exists())
            raw = json.loads((out / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["initial_cash"], "1000000.00")
            self.assertEqual(raw["cost_model"]["bps_1x"], 10)
            self.assertGreater(int(summary["runs"]["H1_1x"]["n_sessions"]), 100)
            # 2x costs must not silently equal a zero-cost run; fees exist on H3.
            self.assertGreater(int(summary["runs"]["H3_1x"]["n_fills"]), 1)
            # Isolated fee overlay on a 1-lot cash buy: 2x cannot beat 1x.
            self.assertLess(
                float(summary["runs"]["CASH_2x"]["final_nav"]),
                float(summary["runs"]["CASH_1x"]["final_nav"]),
            )
            self.assertLess(
                float(summary["runs"]["H1_2x"]["final_nav"]),
                float(summary["runs"]["H1_1x"]["final_nav"]),
            )


class RegenTests(unittest.TestCase):
    def test_synthesizer_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "fx"
            generate_fixtures(dest)
            locked = json.loads((fixtures() / "digests.json").read_text(encoding="utf-8"))
            fresh = json.loads((dest / "digests.json").read_text(encoding="utf-8"))
            self.assertEqual(locked["files"], fresh["files"])
            self.assertEqual(sha256_file(dest / "bars" / "SPY.csv"), locked["files"]["bars/SPY.csv"])


if __name__ == "__main__":
    unittest.main()
