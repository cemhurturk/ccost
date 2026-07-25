import unittest
from datetime import datetime, timezone
from decimal import Decimal

from ccost import aggregate
from ccost.transcript import Record


def rec(model="claude-opus-5", project="-Users-x-proj", session="s1",
        speed="standard", inp=0, out=0, cr=0, cw5=0, cw1=0, ts=None):
    return Record(
        ts=ts or datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc),
        project=project, session=session, model=model, speed=speed,
        input=inp, output=out, cache_read=cr,
        cache_write_5m=cw5, cache_write_1h=cw1,
    )


class TestBucketing(unittest.TestCase):
    def test_groups_by_month(self):
        result = aggregate.aggregate([
            rec(out=1000000, ts=datetime(2026, 6, 15, 12, 0, tzinfo=timezone.utc)),
            rec(out=1000000, ts=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)),
        ], by="month")
        self.assertEqual([b.key for b in result.buckets], ["2026-06", "2026-07"])

    def test_groups_by_model(self):
        result = aggregate.aggregate([
            rec(model="claude-opus-5", out=10),
            rec(model="claude-haiku-4-5", out=10),
            rec(model="claude-opus-5", out=10),
        ], by="model")
        keys = sorted(b.key for b in result.buckets)
        self.assertEqual(keys, ["claude-haiku-4-5", "claude-opus-5"])

    def test_groups_by_project_using_display_name(self):
        result = aggregate.aggregate(
            [rec(project="-Users-cemhurturk-Development-ccost", out=10)],
            by="project",
        )
        self.assertEqual(result.buckets[0].key, "Development-ccost")

    def test_buckets_sum_tokens(self):
        result = aggregate.aggregate([rec(inp=5, out=7), rec(inp=1, out=2)], by="month")
        bucket = result.buckets[0]
        self.assertEqual(bucket.input, 6)
        self.assertEqual(bucket.output, 9)

    def test_cache_write_column_merges_both_ttls(self):
        result = aggregate.aggregate([rec(cw5=100, cw1=200)], by="month")
        self.assertEqual(result.buckets[0].cache_write, 300)


class TestPricing(unittest.TestCase):
    def test_bucket_cost_is_summed(self):
        # 1M output on opus-5 @ $25 = $25, twice = $50
        result = aggregate.aggregate([rec(out=1000000), rec(out=1000000)],
                                     by="month")
        self.assertEqual(result.buckets[0].cost, Decimal("50"))

    def test_unpriced_model_contributes_tokens_but_not_dollars(self):
        result = aggregate.aggregate([
            rec(model="claude-neverwas-1", inp=1000, out=1000),
            rec(model="claude-opus-5", out=1000000),
        ], by="month")
        self.assertEqual(result.buckets[0].cost, Decimal("25"))
        self.assertEqual(result.unpriced["claude-neverwas-1"].tokens, 2000)
        self.assertEqual(result.unpriced["claude-neverwas-1"].rows, 1)

    def test_non_billable_model_is_reported_separately(self):
        result = aggregate.aggregate([rec(model="<synthetic>", inp=5, out=5)],
                                     by="month")
        self.assertEqual(result.non_billable["<synthetic>"].rows, 1)
        self.assertEqual(result.non_billable["<synthetic>"].tokens, 10)
        self.assertNotIn("<synthetic>", result.unpriced)

    def test_bucket_counts_its_unpriced_rows(self):
        result = aggregate.aggregate([
            rec(model="claude-neverwas-1", out=10),
            rec(model="claude-neverwas-1", out=10),
            rec(model="claude-opus-5", out=10),
        ], by="month")
        self.assertEqual(result.buckets[0].unpriced_rows, 2)

    def test_fully_priced_bucket_reports_no_unpriced_rows(self):
        result = aggregate.aggregate([rec(out=10)], by="month")
        self.assertEqual(result.buckets[0].unpriced_rows, 0)

    def test_unpriced_tokens_still_appear_in_bucket_token_columns(self):
        result = aggregate.aggregate([rec(model="claude-neverwas-1", out=1234)],
                                     by="month")
        self.assertEqual(result.buckets[0].output, 1234)
        self.assertEqual(result.buckets[0].cost, Decimal("0"))


class TestMonthOf(unittest.TestCase):
    def test_month_uses_local_time(self):
        r = rec(ts=datetime(2026, 7, 1, 0, 30, tzinfo=timezone.utc))
        expected = r.ts.astimezone().strftime("%Y-%m")
        self.assertEqual(aggregate.month_of(r), expected)


if __name__ == "__main__":
    unittest.main()
