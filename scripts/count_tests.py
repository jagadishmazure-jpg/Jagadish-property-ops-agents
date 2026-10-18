"""Print the real test total (CI docs check regenerates README numbers)."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    out = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q",
         "--co", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT)
    total = 0
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith("test_") or "::" in line:
            total += 1
    # fall back to counting test functions if collection output is quiet
    if total == 0:
        out2 = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "--collect-only",
             "-q", "-p", "no:cacheprovider"],
            capture_output=True, text=True, cwd=ROOT)
        total = sum(1 for l in out2.stdout.splitlines()
                    if "::" in l and "test" in l)
    print(f"total tests: {total}")


if __name__ == "__main__":
    main()
