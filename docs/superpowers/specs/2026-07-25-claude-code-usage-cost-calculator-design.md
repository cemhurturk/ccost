# ccost — Claude Code usage cost calculator

**Date:** 2026-07-25
**Status:** Design approved, not yet implemented

## 1. Purpose

Claude Code does not persist the dollar cost of a session. It persists **token counts** —
every assistant message in `~/.claude/projects/**/*.jsonl` carries a full `usage` block —
and computes cost live at request time (the value the statusline reads as
`.cost.total_cost_usd`). Once the session ends, that number is gone.

`ccost` reconstructs it after the fact.

The user is on a subscription plan, so real spend is fixed and
`~/.claude/stats-cache.json` reports `costUSD: 0` for every model. The number this tool
produces is therefore **notional**: what the same usage would have cost at Anthropic API
list prices. The headline output is that figure compared against the monthly plan price —
a subscription value check.

Non-goals: live/in-session cost (the statusline already shows it), billing reconciliation,
or anything that writes to the transcript directory.

## 2. Source data

```
~/.claude/projects/
  <project-slug>/
    <session-id>.jsonl                          ← main session transcript
    <session-id>/subagents/agent-<id>.jsonl     ← one per subagent, isSidechain: true
```

Scale of the tree this was designed against: on the order of **dozens of project dirs,
a couple thousand transcripts, ~1.5 GB**, spanning several months. Roughly two-thirds of
the files are subagent transcripts. (Any working session drifts these counts upward.)

Every assistant entry carries:

```json
{"type": "assistant", "requestId": "...", "timestamp": "...", "sessionId": "...",
 "message": {"id": "msg_...", "model": "claude-opus-4-8",
   "usage": {"input_tokens": 2, "output_tokens": 1012,
             "cache_creation_input_tokens": 48740, "cache_read_input_tokens": 20628,
             "service_tier": "standard", "speed": "standard",
             "cache_creation": {"ephemeral_5m_input_tokens": 0,
                                "ephemeral_1h_input_tokens": 48740}}}}
```

### 2.1 The duplicate-usage trap

**One API response is written as multiple transcript lines — one per content block — and
every line repeats the same cumulative `usage`.** Observed in a real session:

```
uuid f18ccd95  blocks ['thinking']   out 1012  cc 48740  cr 20628
uuid 5df55c32  blocks ['text']       out 1012  cc 48740  cr 20628
uuid de27f045  blocks ['tool_use']   out 1012  cc 48740  cr 20628
uuid 42b79e67  blocks ['tool_use']   out 1012  cc 48740  cr 20628
```

Summing lines in that one file gave 41,532 output tokens; deduplicating gave 14,562 —
an inflation factor of **2.85×**. In a 20-message file, 15 messages had duplicate lines.

This is the single most important rule in the tool. Everything else is arithmetic.

## 3. Architecture

Single-pass, stateless, zero-dependency. No cache, no database, no network.

```
cli.py ──> transcript.py ──> [Record] ──> aggregate.py ──> report.py
             (walk + parse         (group by month/    (table | json)
              + dedup)              model/project,
                                    price via pricing.py)
```

| Module | Responsibility | Imports |
|---|---|---|
| `pricing.py` | Rate table; `cost(model, speed, date, usage) -> Decimal`. Pure. | — |
| `transcript.py` | Walk transcript root → yield normalized `Record`s. Dedup, aliasing, attribution. | — |
| `aggregate.py` | Group `Record`s into buckets, total tokens and dollars. Pure. | `pricing` |
| `report.py` | Render a bucket set as a table or JSON. Pure. | — |
| `cli.py` | argparse, config load, wiring, exit codes. | all |

No module imports `cli`. `pricing`, `aggregate`, and `report` touch no filesystem, so their
tests are direct function calls.

### 3.1 Layout

```
ccost/__init__.py  __main__.py  cli.py  pricing.py  transcript.py  aggregate.py  report.py
tests/  fixtures/<scenario>/...  test_pricing.py  test_transcript.py  test_aggregate.py
docs/superpowers/specs/
README.md
```

Invoked as `python3 -m ccost`. A shell alias is the suggested convenience; no installer.

### 3.2 Record

```python
Record = namedtuple("Record", "ts project session model speed "
                              "input output cache_read cache_write_5m cache_write_1h")
```

Flat and immutable. `ts` is an aware `datetime`; token fields are `int`.

## 4. Parsing rules

**Dedup key: `(message.id, requestId)`, first occurrence wins.** Applied globally across all
files, not per-file — a resumed or forked session can repeat a message in a second file.
Stored as the concatenated string `"{message_id}|{request_id}"` — exact, no collision risk,
and ~30–50 MB of seen-set across ~500k messages, which is acceptable for a 7s process.

**Line prefilter.** A line is JSON-parsed only if it contains the substring `"usage"`.
This is what makes a full 1.4 GB scan take ~7s instead of minutes; it is a performance
optimization only, and cannot change results (a record without a `usage` key is not billable).

**Subagent rollup.** Files under `<session-id>/subagents/` attribute to the enclosing
project and session. They carry the parent's `sessionId`, so no synthesis is needed — but
they must be walked, or 1,157 files of real token spend vanish from the total.

**Project attribution: the first path component** under the transcript root, decoded from
the slug. At least one project dir contains another project slug nested inside it, so a
rule based on the last-or-second-to-last component misattributes.

**Month bucketing uses local time**, not UTC — "what did July cost me" is a wall-clock
question. Documented in `--help`; UTC bucketing is not offered until someone wants it.

**Model aliasing.** Bare `haiku` / `sonnet` / `opus` appear in some transcripts and are
mapped to the current model in that tier (`claude-haiku-4-5`, `claude-sonnet-5`,
`claude-opus-5`). **Known approximation:** a bare `opus` written months ago resolved to
whatever was current *then*, which may be a cheaper or pricier model than today's. Observed
frequency is low (~50 rows in a 60-file sample), so the error is small, but it is real and
should not be presented as exact.

## 5. Pricing

`tokens / 1_000_000 × rate`, computed in `Decimal`. Float accumulation across hundreds of
thousands of rows drifts by real amounts at this scale; rounding to cents happens once, at
display time, half-up.

Rates per million tokens (input / output):

| Model | Input | Output |
|---|---|---|
| `claude-fable-5`, `claude-mythos-5` | $10 | $50 |
| `claude-opus-5`, `-4-8`, `-4-7`, `-4-6` | $5 | $25 |
| `claude-sonnet-5` | $3 (intro $2 through 2026-08-31) | $15 (intro $10) |
| `claude-sonnet-4-6` | $3 | $15 |
| `claude-haiku-4-5` | $1 | $5 |

Derived rates, all multipliers on the model's **input** rate:

- **Cache read** — 0.1×
- **Cache write, 5-minute TTL** — 1.25×, from `cache_creation.ephemeral_5m_input_tokens`
- **Cache write, 1-hour TTL** — 2×, from `cache_creation.ephemeral_1h_input_tokens`

The two write tiers are priced separately rather than blended; the transcripts record the
split, and this session's data is heavily 1-hour (the 2× tier), so blending would understate.

**Fast mode.** `usage.speed == "fast"` on Opus 5 reprices to $10/$50. Detected per message.

**Sonnet 5 intro pricing** is selected by the message's own date, since the history straddles
the 2026-08-31 cutoff.

The rate table is one dict with a comment citing the pricing docs and the date it was
captured. A rate change is a one-line edit.

### 5.1 Unpriced models

Two distinct cases, reported in the same block:

- **Unpriced** — `claude-opus-4-5`, `claude-sonnet-4-5`, `claude-opus-4-1` appear in the data
  but have no published rate in the current reference. Their dollars are unknown.
- **Non-billable** — `<synthetic>` is a harness-generated pseudo-model that was never charged.
  Its dollars are known to be zero.

Policy for both: **count their tokens, exclude their dollars, and list them explicitly** below
the table, labelled by case so the two aren't conflated. The headline figure is never silently understated by a model the table doesn't know.
The same path handles any future model id, so an unrecognized model degrades to a visible
note rather than a crash or a zero.

## 6. Plan comparison

Config at `~/.config/ccost/config.json`:

```json
{ "plan_usd_per_month": 200 }
```

Overridable with `--plan-usd`. **If absent, the tool runs normally and omits the PLAN and
MULTIPLE columns** — a missing config is not an error.

Each month with any activity is charged one full plan price. The month containing today is
marked `*` (partial) and still charged in full, which understates its multiple — a
deliberately conservative choice.

## 7. Output

Default (`--by month`), figures illustrative:

```
Claude Code usage — API-equivalent cost
812 transcripts · 23 projects · scanned in 3.1s

MONTH     INPUT     OUTPUT    CACHE-R    CACHE-W   API-EQUIV    PLAN   MULTIPLE
2026-06    1.8M       6.2M     310.4M      28.1M   $1,204.66    $200       6.0x
2026-07*   0.9M       4.1M     205.7M      15.3M     $811.34    $200       4.1x
                                                   ─────────
TOTAL                                              $2,016.00    $400       5.0x

Unpriced (tokens counted, dollars excluded):
  claude-opus-4-5   2.1M tokens
  <synthetic>       12 rows
* partial month
```

Flags: `--by month|model|project` · `--since YYYY-MM` · `--project <slug>` · `--json`
· `--plan-usd N` · `--root <path>` (defaults to `~/.claude/projects`; makes tests trivial).

`--json` emits the same aggregates as machine-readable output, dollars as decimal strings.

## 8. Failure behavior

Never crash on a malformed transcript; always report what was dropped.

| Condition | Behavior |
|---|---|
| Unparseable JSON line | Skip, count, report total under the table |
| Unreadable / permission-denied file | Warn to stderr, continue |
| Missing `usage` subfield | Treat as 0 |
| Unknown model | Tokens counted, dollars excluded, listed (§5.1) |
| Transcript root missing or empty | Clear message, exit 0 |
| Invalid config JSON | Warn, fall back to no-plan mode |

Skipped-line and skipped-file counts print with every run, so a silently shrinking total is
impossible to miss.

## 9. Testing

Stdlib `unittest` — `python3 -m unittest discover`. The system interpreter is Python 3.9.6
with no pytest and no venv, so this runs with zero setup. Written test-first, per hazard.

Filesystem fixtures are small hand-written `.jsonl` trees under `tests/fixtures/`:

1. **The 2.85× trap** — four lines sharing one `(message.id, requestId)` across
   thinking/text/tool_use blocks; assert usage counts exactly once.
2. **Cross-file duplicate** — same message in two session files; assert counted once.
3. **Subagent rollup** — a `subagents/agent-*.jsonl` attributing to its parent project.
4. **Nested project slug** — the directory shape that breaks last-component attribution.
5. **Malformed line mid-file** — surrounding records still count; skip counter increments.
6. **Unknown model** — lands in "unpriced", contributes tokens but not dollars.

Pure-function tests need no fixtures:

7. 5m vs 1h cache writes price at 1.25× and 2× of input rate.
8. Cache reads price at 0.1×.
9. Fast-mode Opus 5 reprices to $10/$50.
10. Sonnet 5 on either side of 2026-08-31 picks intro vs standard rate.
11. Decimal accumulation over many rows matches an exact expected total.
12. Month bucketing uses local time and marks the current month partial.

## 10. Rejected alternatives

**Incremental cache** (per-file digest → memoized aggregates). Solves a slow-first-run
problem that a benchmark says does not exist: a full 1.4 GB scan is ~7s, because the
substring prefilter rejects most lines before parsing. A cache would trade six seconds for
stale-cache bugs. Reconsider only if a scan exceeds ~30s.

**Extract to SQLite, then query.** Attractive for ad-hoc analysis later, but a second moving
part and a schema to migrate for a job that finishes in 7s. `--json` covers the
pipe-it-elsewhere case.

**Reading `stats-cache.json` instead of transcripts.** It has a `costUSD` field, but it is
`0` for every model on a subscription and is aggregated per-model with no month, project, or
session dimension. Useless for this purpose.

## 11. Open items

- Rates are captured 2026-07-25. There is no automatic refresh; the table is versioned in git
  and edited by hand when pricing changes.
- Bare-alias resolution (§4) is an approximation with a known small error.
- No per-session breakdown in v1. `--by project` plus `--json` covers most of that need; add
  `--by session` if the project view proves too coarse.
