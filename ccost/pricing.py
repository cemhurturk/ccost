"""Rate table and cost arithmetic. Pure: no filesystem, no network.

Rates captured 2026-07-25 from the Anthropic pricing reference, in USD per
million tokens. Claude 5.5 rates verified 2026-11-10 at
https://platform.claude.com/docs/en/about-claude/pricing
Update the rate tables by hand when pricing changes.
"""
from datetime import date
from decimal import Decimal
from typing import Dict, Optional, Tuple

# Bare aliases appear in some transcripts. They resolved to whatever was
# current when the message was written, which may differ from today's model
# in that tier. Known approximation; see spec section 4.
ALIASES = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
    # Pre-4.6 models carry a date in the id; the docs publish rates against
    # the dateless alias, so fold them together here.
    "claude-opus-4-5-20251101": "claude-opus-4-5",
    "claude-sonnet-4-5-20250929": "claude-sonnet-4-5",
    "claude-opus-4-1-20250805": "claude-opus-4-1",
    "claude-haiku-4-5-20251001": "claude-haiku-4-5",
}

# Harness-generated pseudo-models. Never charged; dollars are known to be zero.
NON_BILLABLE = {"<synthetic>"}

# model -> (input $/MTok, output $/MTok)
RATES = {
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    "claude-fable-5": (Decimal("10"), Decimal("50")),
    "claude-mythos-5": (Decimal("10"), Decimal("50")),
    "claude-opus-5": (Decimal("5"), Decimal("25")),
    "claude-opus-4-8": (Decimal("5"), Decimal("25")),
    "claude-opus-4-7": (Decimal("5"), Decimal("25")),
    "claude-opus-4-6": (Decimal("5"), Decimal("25")),
    "claude-sonnet-5": (Decimal("3"), Decimal("15")),
    "claude-sonnet-4-6": (Decimal("3"), Decimal("15")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5")),
    # Legacy models, still served. Rates from the same reference.
    "claude-opus-4-5": (Decimal("5"), Decimal("25")),
    "claude-sonnet-4-5": (Decimal("3"), Decimal("15")),
    "claude-opus-4-1": (Decimal("15"), Decimal("75")),
}  # type: Dict[str, Tuple[Decimal, Decimal]]

# Fast mode runs the same model at premium rates.
FAST_RATES = {
    "claude-opus-5-5": (Decimal("8"), Decimal("40")),
    "claude-opus-5": (Decimal("10"), Decimal("50")),
    "claude-opus-4-8": (Decimal("10"), Decimal("50")),
}  # type: Dict[str, Tuple[Decimal, Decimal]]

# Sonnet 5 introductory pricing, inclusive of the end date.
SONNET_5_INTRO_END = date(2026, 8, 31)
SONNET_5_INTRO = (Decimal("2"), Decimal("10"))

# Multipliers on the model's INPUT rate.
CACHE_READ = Decimal("0.1")
CACHE_READ_OVERRIDES = {
    "claude-opus-5-5": Decimal("0.05"),
    "claude-sonnet-5-5": Decimal("0.05"),
}
HAIKU_5_5_LONG_PROMPT = (Decimal("0.50"), Decimal("2.50"))
HAIKU_5_5_PROMPT_THRESHOLD = 100000
CACHE_WRITE_5M = Decimal("1.25")
CACHE_WRITE_1H = Decimal("2")

MILLION = Decimal("1000000")


def canonical(model):
    # type: (str) -> str
    """Resolve a bare tier alias to a full model id."""
    return ALIASES.get(model, model)


def is_billable(model):
    # type: (str) -> bool
    return canonical(model) not in NON_BILLABLE


def rates_for(model, speed, on_date, prompt_tokens=0):
    # type: (str, str, date, int) -> Optional[Tuple[Decimal, Decimal]]
    """Return (input, output) $/MTok, or None if the model has no known rate."""
    name = canonical(model)
    if name in NON_BILLABLE:
        return None
    if name == "claude-haiku-5-5" and prompt_tokens > HAIKU_5_5_PROMPT_THRESHOLD:
        return HAIKU_5_5_LONG_PROMPT
    if speed == "fast" and name in FAST_RATES:
        return FAST_RATES[name]
    if name == "claude-sonnet-5" and on_date <= SONNET_5_INTRO_END:
        return SONNET_5_INTRO
    return RATES.get(name)


def cost(model, speed, on_date, input_tokens, output_tokens,
         cache_read, cache_write_5m, cache_write_1h):
    # type: (str, str, date, int, int, int, int, int) -> Optional[Decimal]
    """Dollar cost of one message. None if the model has no known rate."""
    if not is_billable(model):
        return Decimal("0")
    prompt_tokens = input_tokens + cache_read + cache_write_5m + cache_write_1h
    rates = rates_for(model, speed, on_date, prompt_tokens)
    if rates is None:
        return None
    rate_in, rate_out = rates
    cache_read_multiplier = CACHE_READ_OVERRIDES.get(canonical(model), CACHE_READ)
    units = (
        Decimal(input_tokens) * rate_in
        + Decimal(output_tokens) * rate_out
        + Decimal(cache_read) * rate_in * cache_read_multiplier
        + Decimal(cache_write_5m) * rate_in * CACHE_WRITE_5M
        + Decimal(cache_write_1h) * rate_in * CACHE_WRITE_1H
    )
    return units / MILLION
