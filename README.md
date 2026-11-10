# ccost

Reconstructs the API-equivalent dollar cost of past Claude Code sessions from
the transcripts in `~/.claude/projects`.

Claude Code records token counts, not costs — the live figure the statusline
shows is discarded when a session ends. On a subscription plan real spend is
fixed, so the number here is notional: what the same usage would have cost at
API list prices. Compared against a monthly plan price, that is a value check.

```
Claude Code usage — API-equivalent cost
812 transcripts · 23 projects · scanned in 3.1s

MONTH     INPUT     OUTPUT    CACHE-R    CACHE-W   API-EQUIV    PLAN   MULTIPLE
2026-06    1.8M       6.2M     310.4M      28.1M   $1,204.66    $200       6.0x
2026-07*   0.9M       4.1M     205.7M      15.3M     $811.34    $200       4.1x
                                                   ─────────
TOTAL                                              $2,016.00    $400       5.0x

* partial month
```

(Figures illustrative.)

## Install

Clone and run — there is nothing to install:

    git clone https://github.com/cemhurturk/ccost.git
    cd ccost
    python3 -m ccost

## Usage

    python3 -m ccost                      # monthly breakdown
    python3 -m ccost --by project         # per-project
    python3 -m ccost --by model           # per-model
    python3 -m ccost --since 2026-06      # recent months only
    python3 -m ccost --json               # machine-readable

Set the plan price once, in `~/.config/ccost/config.json`:

    { "plan_usd_per_month": 200 }

Or pass `--plan-usd 200`. Without either, the plan comparison is omitted.

Filtering to one project accepts either the display name or the raw directory
slug. Slugs begin with a dash, so they need the `=` form:

    python3 -m ccost --project Development-ccost
    python3 -m ccost --project=-Users-you-Development-ccost

## Requirements

Python 3.9+. No third-party dependencies.

## Tests

    python3 -m unittest discover -s tests -t . -v

## How it works

A single pass over every `.jsonl` under the transcript root. No cache, no
database, no network — a full 1.4 GB tree scans in about five seconds, because
a substring test rejects non-usage lines before any JSON parsing.

The one subtlety worth knowing: **a single API response is written to the
transcript as several lines** — one per content block (thinking, text, each
tool call) — and every one of those lines repeats the same cumulative `usage`.
Summing lines therefore overcounts badly; measured against a real corpus of
roughly 100k rows, the inflation factor was about **2.3×**. `ccost` deduplicates on
`(message.id, requestId)` and counts each response once.

Subagent transcripts (`<session>/subagents/agent-*.jsonl`) are included and
roll up to their parent project — on a subagent-heavy workload they are a large
share of real spend.

## Accuracy notes

- Legacy rates were captured 2026-07-25; Claude Opus, Sonnet, and Haiku 5.5
  rates were verified 2026-11-10 against the [Anthropic pricing reference](https://platform.claude.com/docs/en/about-claude/pricing).
  Rates are edited by hand in `ccost/pricing.py`.
  Prompt-cache reads bill at 0.1× the model's input rate (0.05× for Opus and Sonnet 5.5); cache writes at 1.25×
  (5-minute TTL) or 2× (1-hour), priced from the separate fields the transcript
  records rather than blended.
- Haiku 5.5 uses higher rates when a request has more than 100,000 prompt
  tokens, including cache reads and both cache-write tiers.
- Fast-mode messages (`usage.speed == "fast"`) reprice to the premium tier.
- A model with no entry in the rate table contributes tokens but not dollars,
  and is listed under the table. Any period containing such usage is marked
  `+`, meaning its dollar figure is a floor rather than a total — a period is
  never allowed to look confidently priced when part of it was excluded.
- Bare model aliases (`opus`, `sonnet`, `haiku`) resolve to today's model in
  that tier, which may differ from what they resolved to when written.
- Months are bucketed in local time, not UTC.
- This tool only reads. It never writes to `~/.claude/`.

## License

MIT — see [LICENSE](LICENSE).
