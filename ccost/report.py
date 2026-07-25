"""Render aggregate results. Pure: no filesystem, no network."""
import json
from decimal import Decimal, ROUND_HALF_UP

CENTS = Decimal("0.01")


def human_tokens(n):
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0)
    if n >= 1000:
        return "%.1fK" % (n / 1000.0)
    return str(n)


def money(value):
    quantized = Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)
    return "${:,.2f}".format(quantized)


def _total(result):
    total = Decimal("0")
    for bucket in result.buckets:
        total += bucket.cost
    return total


def render_table(result, plan_usd, current_month, stats, elapsed):
    lines = []
    lines.append("Claude Code usage - API-equivalent cost")
    lines.append("%d transcripts * scanned in %.1fs"
                 % (stats.files_scanned, elapsed))
    lines.append("")

    if not result.buckets:
        lines.append("No usage found.")
        return "\n".join(lines)

    show_plan = plan_usd is not None
    header = "%-24s %9s %9s %10s %10s %12s" % (
        "PERIOD", "INPUT", "OUTPUT", "CACHE-R", "CACHE-W", "API-EQUIV")
    if show_plan:
        header += " %9s %9s" % ("PLAN", "MULTIPLE")
    lines.append(header)

    any_incomplete = False
    for bucket in result.buckets:
        label = bucket.key
        if current_month is not None and bucket.key == current_month:
            label += "*"
        if bucket.unpriced_rows:
            # This bucket's dollars exclude usage we have no rate for, so the
            # figure is a floor. Saying so beats printing a confident number.
            label += "+"
            any_incomplete = True
        row = "%-24s %9s %9s %10s %10s %12s" % (
            label[:24],
            human_tokens(bucket.input), human_tokens(bucket.output),
            human_tokens(bucket.cache_read), human_tokens(bucket.cache_write),
            money(bucket.cost),
        )
        if show_plan:
            multiple = bucket.cost / plan_usd if plan_usd else Decimal("0")
            row += " %9s %8.1fx" % (money(plan_usd), multiple)
        lines.append(row)

    total = _total(result)
    total_row = "%-24s %9s %9s %10s %10s %12s" % (
        "TOTAL", "", "", "", "", money(total))
    if show_plan:
        plan_total = plan_usd * len(result.buckets)
        multiple = total / plan_total if plan_total else Decimal("0")
        total_row += " %9s %8.1fx" % (money(plan_total), multiple)
    lines.append(total_row)

    if result.unpriced:
        lines.append("")
        lines.append("Unpriced - no published rate, dollars unknown and excluded:")
        for model in sorted(result.unpriced):
            tally = result.unpriced[model]
            lines.append("  %-28s %10s tokens  (%d rows)"
                         % (model, human_tokens(tally.tokens), tally.rows))

    if result.non_billable:
        lines.append("")
        lines.append("Non-billable - known to cost zero:")
        for model in sorted(result.non_billable):
            tally = result.non_billable[model]
            lines.append("  %-28s %10s tokens  (%d rows)"
                         % (model, human_tokens(tally.tokens), tally.rows))

    if stats.lines_skipped or stats.files_unreadable:
        lines.append("")
        lines.append("Skipped: %d unparseable lines, %d unreadable files"
                     % (stats.lines_skipped, stats.files_unreadable))

    footnotes = []
    if current_month is not None:
        footnotes.append("* partial month")
    if any_incomplete:
        footnotes.append("+ includes usage from unpriced models - the dollar "
                         "figure is a floor, not a total")
    if footnotes:
        lines.append("")
        lines.extend(footnotes)

    return "\n".join(lines)


def render_json(result, plan_usd):
    payload = {
        "buckets": [
            {
                "key": b.key,
                "input_tokens": b.input,
                "output_tokens": b.output,
                "cache_read_tokens": b.cache_read,
                "cache_write_tokens": b.cache_write,
                "cost_usd": str(Decimal(b.cost).quantize(
                    CENTS, rounding=ROUND_HALF_UP)),
                "unpriced_rows": b.unpriced_rows,
            }
            for b in result.buckets
        ],
        "total_usd": str(_total(result).quantize(CENTS, rounding=ROUND_HALF_UP)),
        "plan_usd_per_month": str(plan_usd) if plan_usd is not None else None,
        "unpriced": {m: {"tokens": t.tokens, "rows": t.rows}
                     for m, t in result.unpriced.items()},
        "non_billable": {m: {"tokens": t.tokens, "rows": t.rows}
                         for m, t in result.non_billable.items()},
    }
    return json.dumps(payload, indent=2, sort_keys=True)
