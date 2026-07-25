import io
import json
import unittest
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from ccost import cli

FIXTURES = Path(__file__).parent / "fixtures"


def run(args):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = cli.main(args)
    return code, buffer.getvalue()


class TestConfig(unittest.TestCase):
    def test_reads_plan_from_config(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text('{"plan_usd_per_month": 200}')
            self.assertEqual(cli.load_plan_usd(path), Decimal("200"))

    def test_missing_config_returns_none(self):
        self.assertIsNone(cli.load_plan_usd(Path("/nope/config.json")))

    def test_malformed_config_returns_none(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{ not json")
            self.assertIsNone(cli.load_plan_usd(path))


class TestMain(unittest.TestCase):
    def test_runs_against_fixture_tree(self):
        code, out = run(["--root", str(FIXTURES / "dupes")])
        self.assertEqual(code, 0)
        self.assertIn("API-equivalent", out)

    def test_dedup_survives_end_to_end(self):
        # 1 deduplicated response = $0.0273, which renders as $0.03.
        # If dedup broke, it would be 4x that and render as $0.11.
        code, out = run(["--root", str(FIXTURES / "dupes"), "--json"])
        payload = json.loads(out)
        self.assertEqual(payload["total_usd"], "0.03")

    def test_json_flag_emits_valid_json(self):
        code, out = run(["--root", str(FIXTURES / "unknown"), "--json"])
        payload = json.loads(out)
        self.assertIn("claude-neverwas-1", payload["unpriced"])

    def test_missing_root_exits_zero(self):
        code, out = run(["--root", str(FIXTURES / "nope")])
        self.assertEqual(code, 0)
        self.assertIn("No usage", out)

    def test_since_filters_earlier_months(self):
        code, out = run(["--root", str(FIXTURES / "dupes"), "--since", "2026-08"])
        self.assertIn("No usage", out)

    def test_project_filter_accepts_raw_slug(self):
        # Real slugs start with a dash, so the equals form is required —
        # argparse would otherwise read the value as a flag.
        code, out = run(["--root", str(FIXTURES / "nested"),
                         "--project=-Users-x-outer", "--json"])
        payload = json.loads(out)
        self.assertEqual(len(payload["buckets"]), 1)

    def test_project_filter_accepts_display_name(self):
        code, out = run(["--root", str(FIXTURES / "nested"),
                         "--project", "outer", "--json"])
        payload = json.loads(out)
        self.assertEqual(len(payload["buckets"]), 1)

    def test_project_filter_excluding_everything_is_empty(self):
        code, out = run(["--root", str(FIXTURES / "nested"),
                         "--project", "nothing"])
        self.assertIn("No usage", out)

    def test_plan_usd_flag_adds_multiple_column(self):
        code, out = run(["--root", str(FIXTURES / "dupes"), "--plan-usd", "200"])
        self.assertIn("MULTIPLE", out)

    def test_by_model_groups_by_model(self):
        code, out = run(["--root", str(FIXTURES / "unknown"),
                         "--by", "model", "--json"])
        payload = json.loads(out)
        keys = sorted(b["key"] for b in payload["buckets"])
        self.assertEqual(keys, ["<synthetic>", "claude-neverwas-1"])


if __name__ == "__main__":
    unittest.main()
