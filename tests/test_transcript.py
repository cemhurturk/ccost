import unittest
from pathlib import Path

from ccost import transcript

FIXTURES = Path(__file__).parent / "fixtures"


class TestDedup(unittest.TestCase):
    def test_one_response_split_across_blocks_counts_once(self):
        records, stats = transcript.scan(FIXTURES / "dupes")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].output, 1000)
        self.assertEqual(records[0].cache_write_1h, 200)
        self.assertEqual(stats.duplicates_dropped, 3)

    def test_same_message_in_two_files_counts_once(self):
        records, stats = transcript.scan(FIXTURES / "crossfile")
        self.assertEqual(len(records), 1)
        self.assertEqual(stats.duplicates_dropped, 1)


class TestAttribution(unittest.TestCase):
    def test_subagent_file_attributes_to_parent_project(self):
        records, _ = transcript.scan(FIXTURES / "subagents")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].project, "-Users-x-proj")
        self.assertEqual(records[0].session, "sess-1")

    def test_nested_slug_uses_first_path_component(self):
        records, _ = transcript.scan(FIXTURES / "nested")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].project, "-Users-x-outer")

    def test_display_project_strips_user_prefix(self):
        self.assertEqual(
            transcript.display_project("-Users-x-Development-ccost"),
            "Development-ccost",
        )

    def test_display_project_leaves_unrecognized_slug_alone(self):
        self.assertEqual(transcript.display_project("plain-name"), "plain-name")


class TestResilience(unittest.TestCase):
    def test_malformed_line_is_skipped_and_counted(self):
        records, stats = transcript.scan(FIXTURES / "malformed")
        self.assertEqual(len(records), 2)
        self.assertEqual(stats.lines_skipped, 1)

    def test_non_assistant_rows_are_ignored(self):
        records, _ = transcript.scan(FIXTURES / "noise")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].output, 2)

    def test_missing_root_returns_empty(self):
        records, stats = transcript.scan(FIXTURES / "does-not-exist")
        self.assertEqual(records, [])
        self.assertEqual(stats.files_scanned, 0)


class TestParsing(unittest.TestCase):
    def test_unknown_and_synthetic_models_still_produce_records(self):
        records, _ = transcript.scan(FIXTURES / "unknown")
        models = sorted(r.model for r in records)
        self.assertEqual(models, ["<synthetic>", "claude-neverwas-1"])

    def test_timestamp_with_trailing_z_parses_to_aware_datetime(self):
        records, _ = transcript.scan(FIXTURES / "dupes")
        ts = records[0].ts
        self.assertIsNotNone(ts.tzinfo)
        self.assertEqual(ts.year, 2026)
        self.assertEqual(ts.month, 7)

    def test_speed_defaults_to_standard_when_absent(self):
        records, _ = transcript.scan(FIXTURES / "crossfile")
        self.assertEqual(records[0].speed, "standard")

    def test_absent_cache_fields_default_to_zero(self):
        records, _ = transcript.scan(FIXTURES / "crossfile")
        r = records[0]
        self.assertEqual((r.cache_read, r.cache_write_5m, r.cache_write_1h), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
