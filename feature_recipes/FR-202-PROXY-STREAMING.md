# Feature Recipe FR-202: Transparent Proxy SSE Streaming & Token Extraction

## 1. Goal
Support Server-Sent Events (SSE `text/event-stream`) streaming in the transparent proxy for real-time CLI coding tools.

## 2. Technical Requirements
1. Inspect `stream: true` in request body or `text/event-stream` in response headers.
2. Forward HTTP chunks in real time to the client without buffering latency.
3. Parse streaming event blocks on the fly (`event: message_start`, `event: message_delta`, `event: content_block_delta`):
   - Extract input tokens from `message_start.message.usage`.
   - Extract output tokens from `message_delta.usage`.
4. Ingest completed request metrics into `UsageDatabase` upon stream termination.

## 3. Verification Criteria
- Streams chunks without disconnection.
- Captures input and output tokens accurately at stream end.
