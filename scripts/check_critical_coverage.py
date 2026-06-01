"""Fail CI when security/protocol modules fall below the critical coverage gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

CRITICAL_PATHS = (
    "plenipo/client/relay.py",
    "plenipo/did/resolve.py",
    "plenipo/crypto/signing_input.py",
    "plenipo/payments/__init__.py",
    "plenipo/mcp/runtime.py",
    "plenipo/mcp/server.py",
)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _percent(summary: dict[str, object]) -> float:
    value = summary.get("percent_covered_display", summary.get("percent_covered", 0.0))
    if isinstance(value, str):
        return float(value.rstrip("%"))
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_critical_coverage.py COVERAGE_JSON THRESHOLD", file=sys.stderr)
        return 2

    coverage_path = Path(sys.argv[1])
    threshold = float(sys.argv[2])
    report = json.loads(coverage_path.read_text(encoding="utf-8"))
    files = {_normalize(path): data for path, data in report.get("files", {}).items()}

    failures: list[str] = []
    for critical_path in CRITICAL_PATHS:
        matched = [
            (path, data)
            for path, data in files.items()
            if path == critical_path or path.endswith(f"/{critical_path}")
        ]
        if not matched:
            failures.append(f"{critical_path}: missing from coverage report")
            continue

        for path, data in matched:
            percent = _percent(data.get("summary", {}))
            if percent < threshold:
                failures.append(f"{path}: {percent:.1f}% below {threshold:.1f}%")

    if failures:
        for failure in failures:
            print(f"Critical coverage failed: {failure}", file=sys.stderr)
        return 1

    print(f"Critical coverage gate passed at {threshold:.1f}%.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
