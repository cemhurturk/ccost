import unittest
from datetime import date
from decimal import Decimal

from ccost import pricing


class TestRates(unittest.TestCase):
    def test_opus_5_standard_rates(self):
        self.assertEqual(
            pricing.rates_for("claude-opus-5", "standard", date(2026, 7, 1)),
            (Decimal("5"), Decimal("25")),
        )

    def test_fable_5_rates(self):
        self.assertEqual(
            pricing.rates_for("claude-fable-5", "standard", date(2026, 7, 1)),
            (Decimal("10"), Decimal("50")),
        )

    def test_haiku_rates(self):
        self.assertEqual(
            pricing.rates_for("claude-haiku-4-5", "standard", date(2026, 7, 1)),
            (Decimal("1"), Decimal("5")),
        )

    def test_fast_mode_opus_5_reprices(self):
        self.assertEqual(
            pricing.rates_for("claude-opus-5", "fast", date(2026, 7, 1)),
            (Decimal("10"), Decimal("50")),
        )

    def test_sonnet_5_intro_rate_before_cutoff(self):
        self.assertEqual(
            pricing.rates_for("claude-sonnet-5", "standard", date(2026, 8, 31)),
            (Decimal("2"), Decimal("10")),
        )

    def test_sonnet_5_standard_rate_after_cutoff(self):
        self.assertEqual(
            pricing.rates_for("claude-sonnet-5", "standard", date(2026, 9, 1)),
            (Decimal("3"), Decimal("15")),
        )

    def test_unknown_model_has_no_rates(self):
        self.assertIsNone(
            pricing.rates_for("claude-neverwas-1", "standard", date(2026, 7, 1))
        )

    def test_legacy_opus_4_5_rates(self):
        self.assertEqual(
            pricing.rates_for("claude-opus-4-5", "standard", date(2026, 1, 1)),
            (Decimal("5"), Decimal("25")),
        )

    def test_legacy_opus_4_1_is_the_expensive_tier(self):
        self.assertEqual(
            pricing.rates_for("claude-opus-4-1", "standard", date(2026, 1, 1)),
            (Decimal("15"), Decimal("75")),
        )

    def test_dated_model_id_resolves_to_its_alias_rate(self):
        # Transcripts record the dated id; the docs price the dateless alias.
        self.assertEqual(
            pricing.rates_for("claude-sonnet-4-5-20250929", "standard",
                              date(2026, 1, 1)),
            (Decimal("3"), Decimal("15")),
        )


class TestAliases(unittest.TestCase):
    def test_bare_aliases_resolve_to_current_tier(self):
        self.assertEqual(pricing.canonical("opus"), "claude-opus-5")
        self.assertEqual(pricing.canonical("sonnet"), "claude-sonnet-5")
        self.assertEqual(pricing.canonical("haiku"), "claude-haiku-4-5")

    def test_full_id_passes_through(self):
        self.assertEqual(pricing.canonical("claude-opus-4-8"), "claude-opus-4-8")


class TestBillable(unittest.TestCase):
    def test_synthetic_is_not_billable(self):
        self.assertFalse(pricing.is_billable("<synthetic>"))

    def test_real_model_is_billable(self):
        self.assertTrue(pricing.is_billable("claude-opus-5"))


class TestCost(unittest.TestCase):
    D = date(2026, 7, 1)

    def test_input_and_output_priced_per_mtok(self):
        # 1M input @ $5 + 1M output @ $25 = $30
        got = pricing.cost("claude-opus-5", "standard", self.D,
                           1000000, 1000000, 0, 0, 0)
        self.assertEqual(got, Decimal("30"))

    def test_cache_read_is_one_tenth_of_input(self):
        # 1M cache read @ 0.1 x $5 = $0.50
        got = pricing.cost("claude-opus-5", "standard", self.D,
                           0, 0, 1000000, 0, 0)
        self.assertEqual(got, Decimal("0.5"))

    def test_cache_write_5m_is_1_25x_input(self):
        got = pricing.cost("claude-opus-5", "standard", self.D,
                           0, 0, 0, 1000000, 0)
        self.assertEqual(got, Decimal("6.25"))

    def test_cache_write_1h_is_2x_input(self):
        got = pricing.cost("claude-opus-5", "standard", self.D,
                           0, 0, 0, 0, 1000000)
        self.assertEqual(got, Decimal("10"))

    def test_unknown_model_returns_none(self):
        self.assertIsNone(
            pricing.cost("claude-neverwas-1", "standard", self.D,
                         1000, 1000, 0, 0, 0)
        )

    def test_non_billable_returns_zero(self):
        self.assertEqual(
            pricing.cost("<synthetic>", "standard", self.D, 1000, 1000, 0, 0, 0),
            Decimal("0"),
        )

    def test_decimal_accumulation_is_exact(self):
        total = Decimal("0")
        for _ in range(100000):
            total += pricing.cost("claude-opus-5", "standard", self.D, 0, 3, 0, 0, 0)
        # 100000 x 3 tokens = 300000 output tokens @ $25/MTok = $7.50 exactly
        self.assertEqual(total, Decimal("7.5"))


if __name__ == "__main__":
    unittest.main()
