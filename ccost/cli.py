"""Command line entry point."""
import argparse
import json
import time
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from ccost import aggregate as aggregate_module
from ccost import report as report_module
from ccost import transcript as transcript_module
from ccost.transcript import display_project

DEFAULT_ROOT = Path.home() / ".claude" / "projects"
DEFAULT_CONFIG = Path.home() / ".config" / "ccost" / "config.json"


def load_plan_usd(path):
    # type: (Path) -> Optional[Decimal]
    """Read the monthly plan price. A missing or broken config is not an error."""
    try:
        raw = path.read_text()
    except OSError:
        return None
    try:
        data = json.loads(raw)
        return Decimal(str(data["plan_usd_per_month"]))
    except (ValueError, KeyError, TypeError, InvalidOperation):
        return None


def build_parser():
    parser = argparse.ArgumentParser(
        prog="ccost",
        description="Reconstruct the API-equivalent cost of past Claude Code "
                    "sessions from local transcripts.",
    )
    parser.add_argument("--by", choices=["month", "model", "project"],
                        default="month", help="how to group results")
    parser.add_argument("--since", metavar="YYYY-MM",
                        help="ignore activity before this month (local time)")
    parser.add_argument("--project", metavar="NAME",
                        help="restrict to one project, by display name "
                             "(Development-ccost) or raw slug. Raw slugs start "
                             "with a dash, so use --project=-Users-...")
    parser.add_argument("--json", action="store_true",
                        help="emit machine-readable JSON")
    parser.add_argument("--plan-usd", metavar="N",
                        help="monthly subscription price; overrides the config")
    parser.add_argument("--root", metavar="PATH", default=str(DEFAULT_ROOT),
                        help="transcript root (default: ~/.claude/projects)")
    parser.add_argument("--config", metavar="PATH", default=str(DEFAULT_CONFIG),
                        help="config file (default: ~/.config/ccost/config.json)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    if args.plan_usd is not None:
        try:
            plan_usd = Decimal(args.plan_usd)
        except InvalidOperation:
            plan_usd = None
    else:
        plan_usd = load_plan_usd(Path(args.config))

    started = time.time()
    records, stats = transcript_module.scan(Path(args.root))
    elapsed = time.time() - started

    if args.project:
        # Every real slug starts with a dash, which argparse would read as a
        # flag, so match the display name too.
        records = [r for r in records
                   if r.project == args.project
                   or display_project(r.project) == args.project]
    if args.since:
        records = [r for r in records
                   if aggregate_module.month_of(r) >= args.since]

    result = aggregate_module.aggregate(records, by=args.by)

    if args.json:
        print(report_module.render_json(result, plan_usd))
        return 0

    current_month = None
    if args.by == "month":
        current_month = datetime.now().astimezone().strftime("%Y-%m")
    print(report_module.render_table(result, plan_usd, current_month,
                                     stats, elapsed))
    return 0
