# Feature Recipe: FR-1005 - Canonical Data Contracts & Model-Specific Pricing Matrix

## Overview
This feature recipe formalizes Ticket AIUM-1005. It establishes zero-external-dependency canonical data contracts (`backend/contracts/models.py`), a comprehensive model-specific pricing and prompt cache multiplier matrix (`backend/contracts/pricing.py`), and unified cost calculation and cloud-savings estimation helpers across the AI Usage Monitor system.

---

## Technical Specifications & Scope of Changes

### 1. `backend/contracts/models.py`
Zero-dependency typed dataclasses using Python standard library `dataclasses`:
- **`UsageEventContract`**:
  - Encapsulates discrete token usage events across all providers.
  - Fields: `provider`, `input_tokens`, `output_tokens`, `total_tokens`, `cache_creation_tokens`, `cache_read_tokens`, `cost_usd`, `model`, `session_id`, `external_id`, `source`, `access_route`, `account_id`, `node_id`, `recorded_at`.
  - Automatically computes `total_tokens` as the sum of I/O and cache tokens if omitted (`__post_init__`).
  - Automatically invokes `calculate_event_cost` if `cost_usd` is zero/omitted and token counts are present.
  - Provides `.to_dict()` and `.from_dict()` for JSON serialization and deserialization.
- **`TelemetrySeriesPoint`**:
  - Discrete time bucket or snapshot point in an analytical telemetry series.
  - Fields: `bucket_utc`, `label`, `tokens`, `cost_usd`, `requests`, `is_cumulative`.
  - Includes `.to_dict()` and `.from_dict()`.
- **`TelemetrySeries`**:
  - Ordered collection of telemetry points for multi-series trend visualizations.
  - Fields: `series_id`, `label`, `provider`, `scope`, `color`, `points`, `total_tokens`, `total_cost_usd`.
  - Normalizes points from dictionaries if needed and auto-computes `total_tokens` and `total_cost_usd` when omitted.
- **`ProviderQuotaSnapshot`**:
  - Normalized snapshot of provider quotas, session/weekly balances, burn rates, and pacing status.
  - Fields: `provider`, `status`, `session_used_pct`, `session_remaining_pct`, `weekly_used_pct`, `weekly_remaining_pct`, `session_reset_str`, `weekly_reset_str`, `burn_rate_tok_per_min`, `pacing_status`.
- **`ThemeConfig`**:
  - Standardized UI color palette and styling configuration for widgets and dashboards.
  - Fields: `theme_name`, `primary_color`, `background_color`, `card_bg_color`, `text_color`, `accent_color`, `border_color`, `font_family`.
- **`WidgetConfig`**:
  - Floating desktop widget positioning, dimensions, opacity, refresh cadences, and docking flags.
  - Fields: `widget_id`, `enabled`, `x`, `y`, `width`, `height`, `opacity`, `always_on_top`, `snapped_edge`, `refresh_interval_ms`, `show_sparklines`, `compact_mode`.

### 2. `backend/contracts/pricing.py`
Defines `MODEL_PRICING_PER_M` and provides pricing heuristic helpers:
- **Rate Schema**: `(input_per_m, output_per_m, cache_write_multiplier, cache_read_multiplier)`.
- **Model Tiers**:
  | Model Tier | Input ($/M) | Output ($/M) | Cache Write Multiplier | Cache Read Multiplier |
  | :--- | :--- | :--- | :--- | :--- |
  | Claude Opus 4 / 3 | $15.00 | $75.00 | 1.25x (surcharge) | 0.10x (90% discount) |
  | Claude Sonnet 4 / 3.7 / 3.5 | $3.00 | $15.00 | 1.25x (surcharge) | 0.10x (90% discount) |
  | Claude Haiku 3.5 / 3 | $0.80 | $4.00 | 1.25x (surcharge) | 0.10x (90% discount) |
  | Gemini 2.5 Pro / 1.5 Pro | $1.25 | $5.00 | 1.00x | 0.25x (75% discount) |
  | Gemini 2.5 Flash / 2.0 Flash / 1.5 Flash | $0.15 | $0.60 | 1.00x | 0.25x (75% discount) |
  | OpenAI GPT-4o | $2.50 | $10.00 | 1.00x | 0.50x (50% discount) |
  | OpenAI GPT-4o-mini | $0.15 | $0.60 | 1.00x | 0.50x (50% discount) |
  | OpenAI o1 / o3-mini | $1.10 | $4.40 | 1.00x | 0.50x (50% discount) |
  | M365 Copilot | $0.00 | $0.00 | 1.00x | 1.00x (Seat license) |
  | Ollama / Local / Iris P2P | $0.00 | $0.00 | 1.00x | 1.00x (Zero token fee) |

- **`estimate_cloud_equivalent_savings_usd(input_tokens, output_tokens)`**:
  - Benchmark based on Claude Sonnet reference pricing ($3.00/M in, $15.00/M out).
  - Returns estimated monetary savings for on-premises/local model execution.
- **`calculate_event_cost(provider, model, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)`**:
  - Matches provider and model case-insensitively with prefix/suffix tolerance.
  - Computes base input cost, output cost, cache write cost (`cache_creation_tokens * input_rate * cache_write_mult`), and cache read cost (`cache_read_tokens * input_rate * cache_read_mult`).
  - Returns USD cost rounded to 6 decimal places.

### 3. `backend/providers/gemini.py`
- Updated `ingest_proxy_interaction` to calculate model-specific costs using `calculate_event_cost(provider="gemini", model=model, ...)` with fallback to base flash pricing.

### 4. `backend/storage/reporting_engine.py`
- Updated `get_pivot_metrics` (`ReportingEngineMixin`) to utilize `calculate_event_cost` when folding cross-platform groups where `estimated_cost` is unpopulated.
- Updated `query_historical_report` to compute `estimated_savings_usd` for local providers via `estimate_cloud_equivalent_savings_usd`.

---

## Verification & Automated Test Results
- Suite: `tests/test_canonical_contracts_and_pricing.py`
- Test Count: 25 unit tests
- Pass Rate: 100% (25 passed, 0 failed, 0 errors)
- Execution Time: ~0.10s
