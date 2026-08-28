from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trading_moe_lab.errors import SpecError
from trading_moe_lab.money import D, apply_adverse_price, fee_on_fill, q_money, shares_from_notional
from trading_moe_lab.spec import spec_from_mapping
from trading_moe_lab.frozen_specs import h1_mapping


class MoneyTests(unittest.TestCase):
    def test_rejects_float(self) -> None:
        with self.assertRaises(TypeError):
            D(1.25)  # type: ignore[arg-type]

    def test_quantize_stable(self) -> None:
        self.assertEqual(str(q_money("1.234567891")), "1.23456789")
        self.assertEqual(shares_from_notional("1000.00", "3.00"), 333)

    def test_adverse_and_fee(self) -> None:
        buy = apply_adverse_price("100.0000", "BUY", 5)
        sell = apply_adverse_price("100.0000", "SELL", 5)
        self.assertEqual(str(buy), "100.0500")
        self.assertEqual(str(sell), "99.9500")
        fee = fee_on_fill(10, "100.0000", 10)
        self.assertEqual(str(fee), "1.00000000")


class SpecTests(unittest.TestCase):
    def test_frozen_h1_valid(self) -> None:
        spec = spec_from_mapping(h1_mapping())
        self.assertEqual(spec.venue, "LOCAL_SIM")
        self.assertTrue(spec.spec_hash())
        again = spec_from_mapping(h1_mapping())
        self.assertEqual(spec.spec_hash(), again.spec_hash())

    def test_live_key_forbidden(self) -> None:
        raw = h1_mapping()
        raw["enable_live"] = True
        with self.assertRaises(SpecError):
            spec_from_mapping(raw)

    def test_leverage_forbidden(self) -> None:
        raw = h1_mapping()
        raw["risk"] = dict(raw["risk"])
        raw["risk"]["max_gross_exposure"] = "1.5"
        with self.assertRaises(SpecError):
            spec_from_mapping(raw)
        raw = h1_mapping()
        raw["risk"] = dict(raw["risk"])
        raw["risk"]["vol_cap"] = "1.2"
        with self.assertRaises(SpecError):
            spec_from_mapping(raw)
        raw = h1_mapping()
        raw["risk"] = dict(raw["risk"])
        raw["risk"]["long_only"] = False
        with self.assertRaises(SpecError):
            spec_from_mapping(raw)

    def test_holdout_must_follow_research(self) -> None:
        raw = h1_mapping()
        raw["research_window"] = {"start": "2018-01-02", "end": "2022-06-01"}
        with self.assertRaises(SpecError):
            spec_from_mapping(raw)


if __name__ == "__main__":
    unittest.main()
