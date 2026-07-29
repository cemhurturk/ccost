# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ccost` reconstructs the API-equivalent dollar cost of past Claude Code sessions by
scanning the JSONL transcripts in `~/.claude/projects`. Claude Code records token
counts but discards the cost figure when a session ends; on a subscription plan real
spend is fixed, so the number this produces is **notional** — what the same usage
would have cost at API list prices, compared against a monthly plan price.

Design rationale lives in `docs/superpowers/specs/2026-07-25-claude-code-usage-cost-calculator-design.md`.
Read it before changing parsing or pricing behaviour — it records why several
non-obvious choices were made, including alternatives that were considered and
rejected.

## Commands

```bash
python3 -m ccost                        # monthly breakdown (the default view)
python3 -m ccost --by project|model     # other groupings
python3 -m ccost --json                 # machine-readable
python3 -m ccost --root tests/fixtures/dupes   # run against a fixture instead of real data

python3 -m unittest discover -s tests -t .           # full suite (~0.15s, 74 tests)
python3 -m unittest tests.test_pricing               # one module
python3 -m unittest tests.test_pricing.TestCost.test_cache_read_is_one_tenth_of_input
```

There is no build step, no linter config, and no dependency install. If a change
seems to need a third-party package, it doesn't.

## Hard constraints

- **Python 3.9.6, system interpreter.** No `tomllib`, no `match`, no `X | Y` unions at
  runtime. Annotations use `typing.Optional` / `Tuple` / `Dict`, or comment-style
  `# type:` signatures as the existing code does.
- **Zero third-party dependencies**, including in tests. Tests are stdlib `unittest`;
  there is no pytest and no venv.
- **`datetime.fromisoformat` on 3.9 cannot parse a trailing `Z`.** Every timestamp
  parse must `.replace("Z", "+00:00")` first. This is the most likely runtime bug to
  reintroduce.
- **All money is `Decimal`, never `float`.** Rounding to cents happens once, at render
  time, `ROUND_HALF_UP`.
- **Strictly read-only against `~/.claude/`.** The tool must never write there.

## The invariant everything depends on

**A single API response is written to the transcript as multiple lines — one per
content block (thinking, text, each tool_use) — and every one of those lines repeats
the same cumulative `usage` block.**

Summing lines overcounts. Measured against a real ~100k-row corpus, the inflation
factor was about **2.3×**. `transcript.scan()` deduplicates on `f"{message.id}|{requestId}"`,
first occurrence wins, applied globally across all files (a resumed or forked session
repeats a message in a second file).

`tests/fixtures/dupes/` encodes this case, and `test_cli.test_dedup_survives_end_to_end`
asserts the end-to-end dollar figure. If either starts failing, dedup has regressed and
every number the tool prints is roughly double the truth.

## Architecture

Single-pass, stateless. No cache, no database, no network. A full 1.4 GB tree scans in
about 5 seconds.

```
cli -> transcript.scan() -> [Record] -> aggregate.aggregate() -> report.render_*()
```

| Module | Role | Imports siblings |
|---|---|---|
| `pricing` | Rate table, model aliasing, `cost()` | none |
| `transcript` | Walk tree, parse, dedup, attribute | none |
| `aggregate` | Group into priced buckets | `pricing`, `transcript` |
| `report` | Table / JSON rendering | none |
| `cli` | argparse, config, wiring | all |

`pricing`, `aggregate`, and `report` touch no filesystem — their tests are direct
function calls. Only `transcript` and `cli` do I/O. Keep it that way; it's why the
suite runs in 150ms.

### Parsing rules that look wrong but aren't

- **The `'"usage"' not in line` prefilter** in `scan()` is what makes the scan fast —
  most lines are rejected before any JSON parsing. It cannot change results, since a
  row without a `usage` key is not billable. Don't remove it as "premature
  optimization"; without it the scan takes minutes.
- **Project = the FIRST path component** under the root, not the last. At least one
  project directory contains another project slug nested inside it
  (`tests/fixtures/nested/` reproduces the shape), so a last-component rule
  misattributes those sessions.
- **Subagent transcripts** (`<session>/subagents/agent-*.jsonl`) are included and roll
  up to the parent project. On subagent-heavy workloads they are a large share of real
  spend; skipping them silently undercounts.
- **Months bucket in local time**, not UTC — "what did July cost me" is a wall-clock
  question.

### Pricing model

Rates in `pricing.RATES` are USD per million tokens, captured 2026-07-25 and
**maintained by hand**. Derived rates are multipliers on the model's *input* rate:
cache read 0.1×, cache write 1.25× (5-minute TTL) or 2× (1-hour). The two write tiers
are priced separately from the distinct fields the transcript records — don't blend
them.

`ALIASES` folds bare tier names (`opus`, `sonnet`) and dated model ids
(`claude-opus-4-5-20251101`) onto the id the rate table prices. Pre-4.6 models carry a
date in the id while the docs publish rates against the dateless alias, which is why
that mapping exists.

### Two kinds of "no dollar figure"

Kept deliberately distinct, and the distinction must survive into the output:

- **Unpriced** — a model with no entry in `RATES`. Dollars are *unknown*. Tokens still
  count, dollars are excluded, and the model is listed below the table.
- **Non-billable** — `<synthetic>`, a harness pseudo-model. Dollars are *known to be
  zero*.

Any period containing unpriced rows is marked `+` in the report, meaning its figure is
a floor rather than a total. This exists because a period once rendered as `$6.83`
against 243.8M tokens — a confidently-wrong small number is worse than a visibly
incomplete one. `Bucket.unpriced_rows` carries the per-bucket count that drives it.

## Verifying a change against real data

The suite uses fixtures only. After changing parsing, pricing, or aggregation, also
check the invariant that the total is identical however you group it:

```bash
for g in month model project; do
  python3 -m ccost --by $g --json | python3 -c "import json,sys; print(json.load(sys.stdin)['total_usd'])"
done
```

All three must print the same figure. They won't if a record is being dropped or
double-counted in one grouping path.

## Testing conventions

Fixtures under `tests/fixtures/<scenario>/` are hand-written JSONL trees, one directory
per hazard: `dupes` (the multi-line response), `crossfile` (same message in two
sessions), `subagents`, `nested` (the attribution trap), `malformed` (a broken line
mid-file), `noise` (non-assistant rows), `unknown` (unpriced + non-billable models).
Add a fixture directory when you find a new shape in real data; don't broaden an
existing one, since each is asserted against exact counts.

Use `claude-neverwas-1` as the stand-in for an unpriced model in tests. Real model ids
get added to `RATES` over time, which would silently turn an "unpriced" test into a
priced one.
