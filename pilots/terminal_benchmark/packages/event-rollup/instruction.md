# Author a UTC event-rollup repair benchmark

Input is {"events":[...]} with id, service, timestamp, latency_ms and error. All rows must have nonempty string id/service, an ISO-8601 timestamp with a timezone, a nonnegative integer latency_ms (not a boolean), and a boolean error. Invalid rows invalidate the whole input as {"error":"invalid_input"}. Deduplicate globally by id, retaining the first event. Convert timestamps to UTC before grouping by calendar date and service. Sort groups by date then service. Each result has date, service, count, errors and p95_ms. p95 is nearest-rank: sort latencies and select position ceil(0.95*N), counting from one. Output {"groups":[...]}.

Run `python /workspace/program.py INPUT.json OUTPUT.json`. Read one JSON document from the first path and write one JSON document to the second. Use only Python standard-library dependencies. Preserve the interface; do not edit or rely on evaluator tests.
