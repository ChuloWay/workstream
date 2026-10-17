import json
from pathlib import Path
import sys

import re
from decimal import Decimal

def solve(payload):
    rows = payload.get("transactions") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {"error": "invalid_input"}
    for row in rows:
        if not isinstance(row, dict) or any(not isinstance(row.get(key), str) or not row[key] for key in ("id", "account", "currency")):
            return {"error": "invalid_input"}
        if row.get("status") not in ("posted", "pending") or row.get("kind") not in ("credit", "debit"):
            return {"error": "invalid_input"}
        if not isinstance(row.get("amount"), str) or not re.fullmatch(r"[0-9]{1,18}(?:\.[0-9]{1,2})?", row["amount"]):
            return {"error": "invalid_input"}
    seen, balances = set(), {}
    for row in rows:
        if row["status"] != "posted" or row["id"] in seen:
            continue
        seen.add(row["id"])
        key = (row["account"], row["currency"])
        amount = Decimal(row["amount"])
        balances[key] = balances.get(key, Decimal(0)) + (amount if row["kind"] == "credit" else -amount)
    return {"balances": [{"account": a, "currency": c, "amount": format(value, ".2f")} for (a, c), value in sorted(balances.items())]}

if __name__ == "__main__":
    source, destination = map(Path, sys.argv[1:])
    payload = json.loads(source.read_text(encoding="utf-8"))
    destination.write_text(json.dumps(solve(payload), sort_keys=True), encoding="utf-8")
