# Architecture Decision Record: Model Benchmarking, Quality Evals & Security Testing Suite

**Date**: 2026-10-08  
**Status**: Accepted  
**Authors**: Antigravity Engineering  
**Derived Standard**: KloGnist WoW v2.5.0 / ASD-STE100  
**Epic**: `EPIC-ESTATE-BENCHMARKING`  
**Ticket ID**: `AIUM-609`  

## Context & Problem Statement
As developers deploy workflows across a heterogeneous fleet of models (local Ollama models, Claude 3.7 Sonnet, Gemini 2.0 Flash, GPT-4o, and Copilot), choosing the right model for each task requires objective comparative metrics.
Estate managers currently lack tooling to empirically answer:
1. **Code & Structural Quality**: Does a cheaper or local model produce syntactically valid code and conform to strict JSON schemas?
2. **Speed & Latency**: What is the real Time-To-First-Token (TTFT) and throughput (Tokens-Per-Second, TPS)?
3. **Prompt Security Resistance**: Does the model defend against system prompt leaks, delimiter overrides, and jailbreak attempts?
4. **ROI & Efficiency**: Which model delivers the optimal quality-to-cost ratio for repetitive agentic routines?

## Decision & Design Rationale
1. **Zero-Dependency Benchmark Engine (`backend/analytics/benchmark_engine.py`)**:
   - Implemented strictly with the Python standard library (`ast`, `re`, `json`, `time`, `statistics`).
   - Modular evaluation suites:
     - `coding`: Synthesizes code tasks and evaluates structural AST correctness with `ast.parse()` and logical assertions.
     - `json_schema`: Evaluates instruction following, strict key presence, and type adherence.
     - `retrieval`: Evaluates context recall and canary extraction in high-entropy contexts.
     - `security`: Evaluates resistance to system prompt leakage, role confusion attacks, and delimiter injections.
   - Computes TTFT (ms), Tokens-Per-Second (TPS), pass/fail counts, and normalized score percentages (0.0 to 100.0%).
2. **Database Persistence (`model_evaluations` Table in `backend/storage/database.py`)**:
   - Persists benchmark runs: `id`, `provider`, `model_name`, `suite_name`, `score_pct`, `ttft_ms`, `tokens_per_sec`, `pass_count`, `fail_count`, `details_json`, `recorded_at`.
   - Adds indexed queries for historical trend tracking and aggregated model leaderboards.
3. **Model Leaderboard Algorithm**:
   - Aggregates average quality scores, security resistance, average TTFT, and TPS per model across runs.
   - Computes an overall composite rating (e.g. A+, A, B+, B, C) and cost efficiency indicator.
4. **REST API Endpoints (`backend/server/http_server.py`)**:
   - `POST /api/benchmarks/run`: Executes benchmark suite for a provider/model and records run metrics.
   - `GET /api/benchmarks/results`: Returns historical benchmark run logs.
   - `GET /api/benchmarks/leaderboard`: Returns aggregated comparative model rankings.
5. **Interactive UI View (`frontend/components/benchmark_scorecard.html`)**:
   - **Leaderboard Scorecard**: Comparative table with quality %, security resistance %, TTFT, and TPS.
   - **Run Benchmark Modal / Control Strip**: 1-click trigger to execute eval suites against connected local or cloud models.
   - **Test Details Breakdown**: Expandable inspection of AST syntax validations and injection defense tests.

## Consequences & Verification
- Unit test suite in `tests/test_model_benchmarking_and_evals.py` covering AST code validation, JSON schema conformance, prompt injection defense, database persistence, and REST APIs.
- 100% green test execution with zero external pip or npm dependencies.
