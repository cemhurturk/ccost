import json
import unittest
from decimal import Decimal

from ccost import report
from ccost.aggregate import Bucket, ModelTally, Result
from ccost.transcript import ScanStats


def sample_result(unpriced_rows=(0, 0)):
    return Result(
        buckets=[
            Bucket("2026-06", 2100000, 9800000, 501300000, 44600000,
                   Decimal("3782.55"), unpriced_rows[0]),
            Bucket("2026-07", 1200000, 8400000, 412500000, 38200000,
                   Decimal("3140.22"), unpriced_rows[1]),
        ],
        unpriced={"claude-neverwas-1": ModelTally(2100000, 40)},
        non_billable={"<synthetic>": ModelTally(120, 12)},
    )


class TestFormatting(unittest.TestCase):
    def test_human_tokens_millions(self):
        self.assertEqual(report.human_tokens(1234567), "1.2M")

    def test_human_tokens_thousands(self):
        self.assertEqual(report.human_tokens(1234), "1.2K")

    def test_human_tokens_small(self):
        self.assertEqual(report.human_tokens(12), "12")

    def test_money_rounds_half_up_to_cents(self):
        self.assertEqual(report.money(Decimal("1234.555")), "$1,234.56")

    def test_money_groups_thousands(self):
        self.assertEqual(report.money(Decimal("1000")), "$1,000.00")


class TestTable(unittest.TestCase):
    def setUp(self):
        self.stats = ScanStats()
        self.stats.files_scanned = 1721

    def test_includes_each_bucket_and_total(self):
        out = report.render_table(sample_result(), Decimal("200"), "2026-07",
                                  self.stats, 7.2)
        self.assertIn("2026-06", out)
        self.assertIn("2026-07", out)
        self.assertIn("TOTAL", out)
        self.assertIn("$6,922.77", out)

    def test_multiple_is_total_over_plan_times_active_months(self):
        out = report.render_table(sample_result(), Decimal("200"), "2026-07",
                                  self.stats, 7.2)
        # 6922.77 / (200 * 2 months) = 17.3x
        self.assertIn("17.3x", out)

    def test_current_month_is_marked_partial(self):
        out = report.render_table(sample_result(), Decimal("200"), "2026-07",
                                  self.stats, 7.2)
        self.assertIn("2026-07*", out)
        self.assertIn("partial month", out)

    def test_plan_columns_omitted_without_plan(self):
        out = report.render_table(sample_result(), None, "2026-07",
                                  self.stats, 7.2)
        self.assertNotIn("MULTIPLE", out)
        self.assertNotIn("PLAN", out)

    def test_unpriced_and_non_billable_listed_separately(self):
        out = report.render_table(sample_result(), Decimal("200"), "2026-07",
                                  self.stats, 7.2)
        self.assertIn("Unpriced", out)
        self.assertIn("claude-neverwas-1", out)
        self.assertIn("Non-billable", out)
        self.assertIn("<synthetic>", out)

    def test_skipped_counts_are_surfaced(self):
        self.stats.lines_skipped = 3
        self.stats.files_unreadable = 1
        out = report.render_table(sample_result(), None, None, self.stats, 1.0)
        self.assertIn("3", out)
        self.assertIn("skipped", out.lower())

    def test_empty_result_says_so(self):
        empty = Result(buckets=[], unpriced={}, non_billable={})
        out = report.render_table(empty, None, None, ScanStats(), 0.1)
        self.assertIn("No usage", out)

    def test_bucket_with_unpriced_rows_is_marked_as_a_floor(self):
        out = report.render_table(sample_result(unpriced_rows=(40, 0)),
                                  None, None, self.stats, 1.0)
        self.assertIn("2026-06+", out)
        self.assertNotIn("2026-07+", out)
        self.assertIn("floor, not a total", out)

    def test_no_floor_footnote_when_every_bucket_is_fully_priced(self):
        out = report.render_table(sample_result(), None, None, self.stats, 1.0)
        self.assertNotIn("floor, not a total", out)


class TestJson(unittest.TestCase):
    def test_json_round_trips_with_decimal_strings(self):
        payload = json.loads(report.render_json(sample_result(), Decimal("200")))
        self.assertEqual(payload["buckets"][0]["key"], "2026-06")
        self.assertEqual(payload["buckets"][0]["cost_usd"], "3782.55")
        self.assertEqual(payload["total_usd"], "6922.77")
        self.assertEqual(payload["plan_usd_per_month"], "200")
        self.assertEqual(payload["unpriced"]["claude-neverwas-1"]["tokens"], 2100000)


if __name__ == "__main__":
    unittest.main()
