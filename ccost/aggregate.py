"""Group records into priced buckets. Pure: no filesystem, no network."""
from collections import namedtuple
from decimal import Decimal
from typing import Dict, List

from ccost import pricing
from ccost.transcript import display_project

Bucket = namedtuple(
    "Bucket", "key input output cache_read cache_write cost unpriced_rows")
ModelTally = namedtuple("ModelTally", "tokens rows")
Result = namedtuple("Result", "buckets unpriced non_billable")


def month_of(record):
    """Local-time month. 'What did July cost me' is a wall-clock question."""
    return record.ts.astimezone().strftime("%Y-%m")


def bucket_key(record, by):
    if by == "month":
        return month_of(record)
    if by == "model":
        return pricing.canonical(record.model)
    if by == "project":
        return display_project(record.project)
    raise ValueError("unknown grouping: %r" % (by,))


def _tally(store, model, tokens):
    previous = store.get(model, ModelTally(0, 0))
    store[model] = ModelTally(previous.tokens + tokens, previous.rows + 1)


def aggregate(records, by="month"):
    totals = {}  # type: Dict[str, List]
    unpriced = {}  # type: Dict[str, ModelTally]
    non_billable = {}  # type: Dict[str, ModelTally]

    for record in records:
        key = bucket_key(record, by)
        if key not in totals:
            totals[key] = [0, 0, 0, 0, Decimal("0"), 0]
        slot = totals[key]
        slot[0] += record.input
        slot[1] += record.output
        slot[2] += record.cache_read
        slot[3] += record.cache_write_5m + record.cache_write_1h

        tokens = (record.input + record.output + record.cache_read
                  + record.cache_write_5m + record.cache_write_1h)

        if not pricing.is_billable(record.model):
            _tally(non_billable, record.model, tokens)
            continue

        amount = pricing.cost(
            record.model, record.speed, record.ts.astimezone().date(),
            record.input, record.output, record.cache_read,
            record.cache_write_5m, record.cache_write_1h,
        )
        if amount is None:
            # Unknown model: tokens counted, dollars unknown and excluded.
            # The bucket counter is what lets the report warn that this
            # bucket's dollar figure is a floor rather than a total.
            _tally(unpriced, record.model, tokens)
            slot[5] += 1
            continue
        slot[4] += amount

    buckets = [
        Bucket(key, v[0], v[1], v[2], v[3], v[4], v[5])
        for key, v in sorted(totals.items())
    ]
    return Result(buckets=buckets, unpriced=unpriced, non_billable=non_billable)
