"""
AI Usage Monitor - Model-Specific Pricing Matrix & Cost Engine (AIUM-1005)
Zero-dependency, canonical pricing table and cost calculation helpers across AI providers,
models, and prompt caching tiers.
"""

from typing import Dict, Tuple

# Tuple schema: (input_per_m, output_per_m, cache_write_multiplier, cache_read_multiplier)
RateTuple = Tuple[float, float, float, float]

MODEL_PRICING_PER_M: Dict[str, RateTuple] = {
    # Claude Family
    "claude-opus-4": (15.0, 75.0, 1.25, 0.10),
    "claude-3-opus": (15.0, 75.0, 1.25, 0.10),
    "claude-sonnet-4": (3.0, 15.0, 1.25, 0.10),
    "claude-3-7-sonnet": (3.0, 15.0, 1.25, 0.10),
    "claude-3-5-sonnet": (3.0, 15.0, 1.25, 0.10),
    "claude-3-5-haiku": (0.80, 4.0, 1.25, 0.10),
    "claude-3-haiku": (0.80, 4.0, 1.25, 0.10),

    # Gemini Family
    "gemini-2.5-pro": (1.25, 5.0, 1.0, 0.25),
    "gemini-1.5-pro": (1.25, 5.0, 1.0, 0.25),
    "gemini-2.5-flash": (0.15, 0.60, 1.0, 0.25),
    "gemini-2.0-flash": (0.15, 0.60, 1.0, 0.25),
    "gemini-1.5-flash": (0.15, 0.60, 1.0, 0.25),

    # OpenAI Family
    "gpt-4o": (2.50, 10.0, 1.0, 0.50),
    "gpt-4o-mini": (0.15, 0.60, 1.0, 0.50),
    "o1-mini": (1.10, 4.40, 1.0, 0.50),
    "o3-mini": (1.10, 4.40, 1.0, 0.50),
    "o1": (1.10, 4.40, 1.0, 0.50),

    # M365 Copilot (Enterprise seat subscription)
    "m365-copilot": (0.0, 0.0, 1.0, 1.0),

    # Local / P2P Engines (Zero raw API token fee)
    "ollama": (0.0, 0.0, 1.0, 1.0),
    "local": (0.0, 0.0, 1.0, 1.0),
    "iris-p2p": (0.0, 0.0, 1.0, 1.0),
}


def resolve_pricing_rates(provider: str, model: str) -> RateTuple:
    """
    Resolves (input_per_m, output_per_m, cache_write_mult, cache_read_mult) using case-insensitive
    provider and model substring heuristics.
    """
    p = str(provider or "").strip().lower()
    m = str(model or "").strip().lower()

    # 1. Local / Self-Hosted / P2P
    if (
        p in ("ollama", "lmstudio", "vllm", "oobabooga", "tabby_kobold", "local", "iris", "iris_p2p", "p2p")
        or m.startswith("ollama")
        or "iris" in m
        or "local" in m
    ):
        return (0.0, 0.0, 1.0, 1.0)

    # 2. M365 Copilot Seat
    if (
        p in ("m365", "copilot", "office365", "microsoft", "m365_copilot")
        or "copilot" in m
        or "m365" in m
    ):
        return (0.0, 0.0, 1.0, 1.0)

    # 3. OpenAI Models (Mini must be checked prior to base GPT-4o)
    if p in ("openai", "chatgpt") or m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3") or "openai" in m:
        if "gpt-4o-mini" in m or "4o-mini" in m:
            return (0.15, 0.60, 1.0, 0.50)
        if "gpt-4o" in m or "4o" in m:
            return (2.50, 10.0, 1.0, 0.50)
        if "o1-mini" in m or "o3-mini" in m or "o1" in m or "o3" in m:
            return (1.10, 4.40, 1.0, 0.50)
        return (0.15, 0.60, 1.0, 0.50)

    # 4. Anthropic Claude Models
    if p in ("claude", "anthropic") or "claude" in m or "opus" in m or "sonnet" in m or "haiku" in m:
        if "opus" in m:
            return (15.0, 75.0, 1.25, 0.10)
        if "haiku" in m:
            return (0.80, 4.0, 1.25, 0.10)
        if "sonnet" in m:
            return (3.0, 15.0, 1.25, 0.10)
        # Default Claude fallback: Sonnet
        return (3.0, 15.0, 1.25, 0.10)

    # 5. Google Gemini Models
    if p in ("gemini", "google") or "gemini" in m:
        if "pro" in m:
            return (1.25, 5.0, 1.0, 0.25)
        if "flash" in m:
            return (0.15, 0.60, 1.0, 0.25)
        # Default Gemini fallback: Flash
        return (0.15, 0.60, 1.0, 0.25)

    # 6. Exact or substring match in catalog
    for key, rates in MODEL_PRICING_PER_M.items():
        if key in m or m in key:
            return rates

    # 7. Unmatched fallback
    return (0.0, 0.0, 1.0, 1.0)


def estimate_cloud_equivalent_savings_usd(input_tokens: int, output_tokens: int) -> float:
    """
    Estimates cloud equivalent monetary savings for local models based on the
    industry-standard Sonnet 3.5/3.7 cloud reference tier ($3.00/M input, $15.00/M output).
    Returns cost rounded to 6 decimal places.
    """
    in_tok = max(0, int(input_tokens or 0))
    out_tok = max(0, int(output_tokens or 0))
    savings = (in_tok * 3.0 / 1_000_000.0) + (out_tok * 15.0 / 1_000_000.0)
    return round(savings, 6)


def calculate_event_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> float:
    """
    Calculates estimated cost in USD for a token usage event based on provider,
    model tier, base input/output rates, and cache creation/read multipliers.
    Returns cost rounded to 6 decimal places.
    """
    in_tok = max(0, int(input_tokens or 0))
    out_tok = max(0, int(output_tokens or 0))
    cc_tok = max(0, int(cache_creation_tokens or 0))
    cr_tok = max(0, int(cache_read_tokens or 0))

    input_rate, output_rate, cache_write_mult, cache_read_mult = resolve_pricing_rates(
        provider, model
    )

    base_in_cost = (in_tok * input_rate) / 1_000_000.0
    out_cost = (out_tok * output_rate) / 1_000_000.0
    cache_write_cost = (cc_tok * input_rate * cache_write_mult) / 1_000_000.0
    cache_read_cost = (cr_tok * input_rate * cache_read_mult) / 1_000_000.0

    total_cost = base_in_cost + out_cost + cache_write_cost + cache_read_cost
    return round(total_cost, 6)
