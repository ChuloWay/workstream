import json
from pathlib import Path
import sys

import sqlite3

def solve(payload):
    with sqlite3.connect("records.sqlite") as db:
        db.execute("CREATE TABLE IF NOT EXISTS records (id TEXT PRIMARY KEY, quantity INTEGER NOT NULL)")
        db.commit()
        try:
            db.execute("BEGIN")
            if not isinstance(payload, dict):
                raise ValueError
            rows = payload.get("rows")
            if not isinstance(rows, list):
                raise ValueError
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"] or type(row.get("quantity")) is not int or not 0 <= row["quantity"] <= 2147483647:
                    raise ValueError
                old = db.execute("SELECT quantity FROM records WHERE id = ?", (row["id"],)).fetchone()
                if old is not None and old[0] != row["quantity"]:
                    raise ValueError
                db.execute("INSERT OR IGNORE INTO records VALUES (?, ?)", (row["id"], row["quantity"]))
            db.commit()
            status = "committed"
        except ValueError:
            db.rollback()
            status = "rejected"
        return {"status": status, "rows": [list(row) for row in db.execute("SELECT id, quantity FROM records ORDER BY id")]}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
