import json
from pathlib import Path
import sys

from datetime import datetime, timezone
import math

def solve(payload):
    events = payload.get("events")
    if not isinstance(events, list):
        return {"error": "invalid_input"}
    parsed = []
    for row in events:
        try:
            if not isinstance(row, dict) or any(not isinstance(row.get(k), str) or not row[k] for k in ("id", "service", "timestamp")):
                raise ValueError
            stamp = datetime.fromisoformat(row["timestamp"])
            if stamp.utcoffset() is None or type(row.get("latency_ms")) is not int or row["latency_ms"] < 0 or type(row.get("error")) is not bool:
                raise ValueError
            parsed.append((row, stamp.astimezone(timezone.utc).date().isoformat()))
        except (ValueError, TypeError):
            return {"error": "invalid_input"}
    seen, groups = set(), {}
    for row, day in parsed:
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        groups.setdefault((day, row["service"]), []).append(row)
    return {"groups": [{"date": day, "service": service, "count": len(rows), "errors": sum(r["error"] for r in rows), "p95_ms": sorted(r["latency_ms"] for r in rows)[math.ceil(.95 * len(rows)) - 1]} for (day, service), rows in sorted(groups.items())]}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
