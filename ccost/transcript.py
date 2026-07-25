"""Walk the Claude Code transcript tree and yield deduplicated usage records.

Read-only. Never writes to the transcript directory.
"""
import json
from collections import namedtuple
from datetime import datetime
from typing import List, Optional, Tuple

Record = namedtuple(
    "Record",
    "ts project session model speed "
    "input output cache_read cache_write_5m cache_write_1h",
)


class ScanStats(object):
    def __init__(self):
        self.files_scanned = 0
        self.files_unreadable = 0
        self.lines_skipped = 0
        self.duplicates_dropped = 0


def display_project(slug):
    # type: (str) -> str
    """Strip a leading -Users-<name>- prefix from a project slug for display."""
    parts = slug.split("-")
    # A slug starts with an empty part because of its leading dash.
    if len(parts) >= 4 and parts[0] == "" and parts[1] == "Users":
        return "-".join(parts[3:]) or slug
    return slug


def dedup_key(obj):
    # type: (dict) -> str
    """One API response spans several transcript lines, each repeating the
    same cumulative usage. This key collapses them."""
    message = obj.get("message") or {}
    return "%s|%s" % (message.get("id"), obj.get("requestId"))


def _parse_ts(raw):
    # type: (Optional[str]) -> Optional[datetime]
    if not raw:
        return None
    # Python 3.9's fromisoformat cannot parse a trailing "Z".
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def record_from(obj, project):
    # type: (dict, str) -> Optional[Record]
    if obj.get("type") != "assistant":
        return None
    message = obj.get("message") or {}
    usage = message.get("usage")
    if not usage:
        return None
    ts = _parse_ts(obj.get("timestamp"))
    if ts is None:
        return None
    creation = usage.get("cache_creation") or {}
    return Record(
        ts=ts,
        project=project,
        session=obj.get("sessionId") or "",
        model=message.get("model") or "",
        speed=usage.get("speed") or "standard",
        input=int(usage.get("input_tokens") or 0),
        output=int(usage.get("output_tokens") or 0),
        cache_read=int(usage.get("cache_read_input_tokens") or 0),
        cache_write_5m=int(creation.get("ephemeral_5m_input_tokens") or 0),
        cache_write_1h=int(creation.get("ephemeral_1h_input_tokens") or 0),
    )


def scan(root):
    # type: (object) -> Tuple[List[Record], ScanStats]
    """Scan every .jsonl under root. Returns (records, stats)."""
    stats = ScanStats()
    records = []  # type: List[Record]
    seen = set()

    if not root.exists():
        return records, stats

    for path in sorted(root.rglob("*.jsonl")):
        try:
            relative = path.relative_to(root)
        except ValueError:
            continue
        if not relative.parts:
            continue
        # Project is the FIRST path component: one project directory nests
        # another project slug inside it, so a last-component rule
        # misattributes those sessions.
        project = relative.parts[0]
        try:
            handle = path.open("r", errors="replace")
        except OSError:
            stats.files_unreadable += 1
            continue
        stats.files_scanned += 1
        with handle:
            for line in handle:
                # Cheap reject before any JSON parsing. This is what makes a
                # full 1.4 GB scan take seconds rather than minutes. It cannot
                # change results: a row with no "usage" key is not billable.
                if '"usage"' not in line:
                    continue
                try:
                    obj = json.loads(line)
                except ValueError:
                    stats.lines_skipped += 1
                    continue
                if not isinstance(obj, dict):
                    continue
                record = record_from(obj, project)
                if record is None:
                    continue
                key = dedup_key(obj)
                if key in seen:
                    stats.duplicates_dropped += 1
                    continue
                seen.add(key)
                records.append(record)

    return records, stats
