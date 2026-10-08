# Feature Recipe FR-609: Model Benchmarking, Quality Evaluations & Security Testing Suite

## 1. Goal
Establish an automated benchmarking, quality evaluation, and model security test harness across all connected platforms and local models (Anthropic Claude, Google Gemini, OpenAI ChatGPT, Ollama Local Models, and M365 Copilot). Enable estate managers to quantitatively compare model accuracy, latency, and prompt resistance alongside token costs.

## 2. Technical Requirements
1. **Zero-Dependency Benchmark Test Harness**:
   - Built with Python Standard Library (`http.client`, `urllib.request`, `json`, `time`, `statistics`).
   - Execute standardized test batches across configured model endpoints without third-party frameworks.
2. **Quality & Reasoning Evaluation Modules**:
   - **Coding & Syntax Validity**: Run standard code synthesis tasks with AST parsing (`ast.parse`) and deterministic unit execution.
   - **Instruction Following & JSON Schema Adherence**: Strict JSON validator checking required fields, data types, and enum values.
   - **Context Recall & Needle-in-a-Haystack**: Test retrieval across variable token window lengths (2k, 8k, 32k, 128k).
3. **Latency & Throughput Benchmarking**:
   - Measure TTFT (Time to First Token) on streaming endpoints.
   - Measure sustained output tokens-per-second (TPS) and inference jitter.
4. **Prompt Security & Injection Probing**:
   - Automated injection resistance tests (indirect injection, delimiter breaking, role confusion).
   - System prompt leakage defense checks.
   - Canary token preservation verification.
5. **Storage Schema & REST API**:
   - SQLite table `model_evaluations` tracking `id, provider, model_name, suite_name, score_pct, ttft_ms, tokens_per_sec, pass_count, fail_count, recorded_at`.
   - API endpoints `POST /api/benchmarks/run`, `GET /api/benchmarks/results`, `GET /api/benchmarks/leaderboard`.
6. **Frontend Scorecard View**:
   - Radar and bar charts comparing models across Speed, Quality, Cost Efficiency, and Security.

## 3. Verification Criteria
- [x] Automated test suite validating benchmark execution with mock LLM endpoints (`tests/test_model_benchmarking_and_evals.py`).
- [x] Error handling ensures network timeouts or model faults do not crash the daemon.
- [x] Zero external dependencies (`ast`, `re`, `json`, `time`, `statistics`).
- [x] REST API endpoints `/api/benchmarks/run`, `/api/benchmarks/results`, `/api/benchmarks/leaderboard` verified with green assertions.
- [x] Frontend scorecard component `frontend/components/benchmark_scorecard.html` integrated with dynamic execution and leaderboard rendering.
- [x] Full test pass: 98 / 98 tests green (0 failures, 0 errors).

## 4. Status
**Complete** - Verified under Ways of Work 7-Step Lifecycle Protocol.

