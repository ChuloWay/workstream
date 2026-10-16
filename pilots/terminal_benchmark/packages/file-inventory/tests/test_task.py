"""Independent black-box cases for this original, trusted calibration package."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile


def main():
    program = Path(sys.argv[1]).resolve(strict=True)
    cases = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="benchmark-case-") as directory:
            root = Path(directory)
            for name, content in case.get("files", {}).items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            for index, step in enumerate(case["steps"]):
                input_path, output_path = root / f"input-{index}.json", root / f"output-{index}.json"
                input_path.write_text(json.dumps(step["input"]), encoding="utf-8")
                try:
                    run = subprocess.run(
                        [sys.executable, str(program), str(input_path), str(output_path)],
                        cwd=root, capture_output=True, timeout=5, check=False,
                    )
                except subprocess.TimeoutExpired:
                    raise AssertionError(f"{case['name']} step {index}: program timed out") from None
                if run.returncode != 0 or not output_path.is_file():
                    raise AssertionError(f"{case['name']} step {index}: no successful output")
                try:
                    actual = json.loads(output_path.read_text(encoding="utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    raise AssertionError(f"{case['name']} step {index}: output is not valid UTF-8 JSON") from None
                if actual != step["expected"]:
                    raise AssertionError(f"{case['name']} step {index}: output differs from independent expected value")
                if "database_rows" in step:
                    try:
                        with sqlite3.connect(root / "records.sqlite") as connection:
                            rows = [list(row) for row in connection.execute("SELECT id, quantity FROM records ORDER BY id")]
                    except sqlite3.Error:
                        raise AssertionError(f"{case['name']} step {index}: required database rows are unreadable") from None
                    if rows != step["database_rows"]:
                        raise AssertionError(f"{case['name']} step {index}: durable rows differ")
    print(json.dumps({"cases": len(cases), "status": "passed"}, sort_keys=True))


if __name__ == "__main__":
    main()
