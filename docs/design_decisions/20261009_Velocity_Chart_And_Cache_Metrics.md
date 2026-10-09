# Architecture Decision Record: 24-Hour Velocity Chart Clarification, Idle Zero Baselines & Cache Token Metrics

**Date**: 2026-10-09  
**Status**: Accepted  
**Context**: FR-615 / AIUM-615  

## Context
1. **Velocity Chart Ambiguity**:
   The 24-Hour Token Velocity & Multi-Platform Trends chart on the dashboard displayed a single compound line (solid orange and dashed cyan overlaid) when Claude was the sole active platform with usage. Because idle platforms (Gemini, ChatGPT, Ollama, Copilot) had zero events in the window, their lines were omitted completely. This led to user confusion where the overlaid "Total Combined" line appeared to plot the identical total for all platforms.
2. **Cache Token Metrics Parity (CCUSAGE)**:
   Analysis of `ccusage` demonstrated that Anthropic's Claude Code logs break tokens down into: `input_tokens`, `output_tokens`, `cache_creation_input_tokens`, and `cache_read_input_tokens`. While AI Usage Monitor parsed these values in `scan_local_logs()`, it folded cache tokens into a single input sum without storing them in dedicated columns, missing fine-grained cache efficiency reporting.

## Decisions
1. **Multi-Platform Velocity Chart Clarification**:
   - Update `renderSvgChart()` to compute 24-hour token totals per platform and enrich legend pills with dynamic token badges (`25.3k tok` or `0 t (idle)`).
   - Render idle platforms as subtle zero baselines (`y = 0`) with faint styling so clicking legend pills isolates them cleanly and tooltips indicate `0 tokens (idle)`.
   - When only one provider has active tokens, disambiguate `Total Combined` with explicit tooltips (`Total: X tokens (Provider: 100%)`).
2. **Dedicated Cache Token Storage**:
   - Migrate `usage_events` with `cache_creation_tokens INTEGER DEFAULT 0` and `cache_read_tokens INTEGER DEFAULT 0`.
   - Update `record_usage_event()` to persist these columns.
   - Update `query_historical_reports()` and frontend table components to include dedicated `Cache Create` and `Cache Read` columns.

## Consequences
- The velocity chart immediately clarifies why curves look the way they do, eliminating confusion over solitary active providers.
- Full parity with `ccusage` is achieved, enabling users to inspect prompt cache efficiency and savings directly in AI Usage Monitor without external tools.
