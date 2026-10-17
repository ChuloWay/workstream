import json
from pathlib import Path
import sys

import hashlib

def solve(payload):
    root = Path(payload["root"])
    files = []
    for path in sorted(root.rglob("*"), key=lambda p: p.relative_to(root).as_posix()):
        if path.is_file() and not path.name.endswith(".tmp"):
            content = path.read_bytes()
            files.append({"path": path.relative_to(root).as_posix(), "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    return {"files": files}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
