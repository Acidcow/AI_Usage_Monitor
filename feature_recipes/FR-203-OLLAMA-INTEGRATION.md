# Feature Recipe FR-203: Live Ollama Model Monitor & Local Inference Ingestor

## 1. Goal
Connect to local Ollama runtime on `http://localhost:11434`, detect installed models, and track active local inference.

## 2. Technical Requirements
1. Poll `GET http://localhost:11434/api/tags` to list all installed models, parameter sizes, and quantization levels.
2. Poll `GET http://localhost:11434/api/ps` to detect currently running models loaded into GPU / CPU memory.
3. Allow routing local Ollama requests through `http://127.0.0.1:8766/ollama` to capture prompt tokens and evaluation tokens (`prompt_eval_count`, `eval_count`).
4. Display green status dot and loaded model badge in dashboard and mini widget.

## 3. Verification Criteria
- Accurately identifies all models available on localhost:11434.
- Marks status `ACTIVE` when Ollama is running and `OFFLINE` if stopped.
