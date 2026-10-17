import json
from pathlib import Path
import sys



def solve(payload):
    # Starter defect: ignores all work and returns an empty result.
    return {}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
