import json
from pathlib import Path
import sys

import copy

def merge(base, overrides):
    result = copy.deepcopy(base) if isinstance(base, dict) else {}
    for key, value in overrides.items():
        if value is None:
            result.pop(key, None)
        elif isinstance(value, dict):
            result[key] = merge(result.get(key), value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def solve(payload):
    return {"config": merge(payload["base"], payload["overrides"])}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
