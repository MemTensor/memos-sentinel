"""Phase 1 Apply — Execute batch labeling based on phase1_report.json.

Usage:
    python -m src.phase1_apply              # dry-run (show what would happen)
    python -m src.phase1_apply --execute    # actually apply labels

Uses `gh` CLI to apply labels to issues on MemTensor/MemOS.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

REPORT_FILE = Path(__file__).parent.parent / "phase1_report.json"
REPO = "MemTensor/MemOS"


def apply_labels(execute: bool = False):
    if not REPORT_FILE.exists():
        print(f"ERROR: {REPORT_FILE} not found. Run `python3 -m src.phase1` first.")
        return

    report = json.loads(REPORT_FILE.read_text())
    details = report["details"]

    print(f"{'EXECUTING' if execute else 'DRY-RUN'}: Applying labels to {len(details)} issues")
    print(f"Repository: {REPO}\n")

    applied = 0
    skipped = 0
    errors = []

    for item in details:
        number = item["number"]
        suggested = item["suggested_labels"]
        current = item["current_labels"]

        # Only add labels that don't already exist
        to_add = [l for l in suggested if l not in current]

        if not to_add:
            skipped += 1
            continue

        label_str = ",".join(to_add)

        if execute:
            try:
                result = subprocess.run(
                    ["gh", "issue", "edit", str(number), "--repo", REPO, "--add-label", label_str],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if result.returncode == 0:
                    print(f"  OK  #{number:4d} +[{label_str}]")
                    applied += 1
                else:
                    print(f"  ERR #{number:4d} {result.stderr.strip()}")
                    errors.append({"number": number, "error": result.stderr.strip()})
                # Rate limit: small delay between API calls
                time.sleep(0.5)
            except Exception as e:
                print(f"  ERR #{number:4d} {e}")
                errors.append({"number": number, "error": str(e)})
        else:
            print(f"  [dry] #{number:4d} would add: [{label_str}]")
            applied += 1

    print(f"\n--- Summary ---")
    print(f"  {'Applied' if execute else 'Would apply'}: {applied}")
    print(f"  Skipped (already labeled): {skipped}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for e in errors:
            print(f"    #{e['number']}: {e['error']}")

    if not execute:
        print(f"\nTo execute for real, run: python3 -m src.phase1_apply --execute")


if __name__ == "__main__":
    execute = "--execute" in sys.argv
    apply_labels(execute=execute)
