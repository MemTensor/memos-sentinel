"""Phase 1 — Scan and classify all open issues using Sentinel's classifier + LLM.

Usage:
    python -m src.phase1

Reads issues from data_issues.json (fetched via gh CLI),
runs rule engine + LLM fallback, outputs a classification report.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

# Allow running as `python -m src.phase1` from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.labels.classifier import _classify_type, _classify_module, _classify_priority

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).parent.parent / "data_issues.json"
REPORT_FILE = Path(__file__).parent.parent / "phase1_report.json"

# Set env vars for LLM if not already set (for local dev convenience)
if not os.environ.get("OPENAI_API_KEY"):
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


async def classify_single(issue: dict, use_llm: bool = True) -> dict:
    """Classify a single issue using rule engine + optional LLM fallback."""
    title = (issue.get("title") or "").lower()
    body = (issue.get("body") or "").lower()
    text = f"{title} {body}"

    type_label = _classify_type(text)
    module_label = _classify_module(text)

    # LLM fallback for uncertain cases
    if use_llm and (not type_label or not module_label):
        from src.labels.classifier import _llm_classify
        llm_labels = await _llm_classify(issue, missing_type=not type_label, missing_module=not module_label)
        for l in llm_labels:
            if l in ("plugin", "memos") and not module_label:
                module_label = l
            elif not type_label:
                type_label = l

    priority_label = _classify_priority(text, type_label, module_label)

    # ai-task judgment (rule-based first, LLM for borderline cases)
    can_ai_fix = await _should_ai_task(issue, type_label, module_label, text, use_llm)

    return {
        "number": issue["number"],
        "title": issue["title"],
        "current_labels": [l["name"] for l in issue.get("labels", [])],
        "classified": {
            "type": type_label,
            "module": module_label,
            "priority": priority_label,
        },
        "ai_task": can_ai_fix,
        "suggested_labels": _build_label_set(module_label, can_ai_fix),
    }


async def _should_ai_task(
    issue: dict, type_label: str | None, module_label: str | None, text: str, use_llm: bool
) -> bool:
    """Determine if an issue can be auto-fixed by the agent.

    Two-pass:
    1. Rule-based fast reject/accept
    2. LLM confirmation for borderline cases
    """
    current_labels = [l["name"] for l in issue.get("labels", [])]
    if "ai-task" in current_labels:
        return True

    # Hard NO: discussions, questions, performance tuning, vague enhancements
    if type_label in ("question", "performance"):
        return False
    if type_label == "enhancement":
        return False

    # Hard YES: documentation (translate, typo)
    if type_label == "documentation":
        return True

    # Hard YES: simple refactor
    if any(sig in text for sig in ("refactor", "remove dead", "typo")):
        return True

    # Regression → usually well-defined
    if type_label == "regression":
        return True

    # Bug: rule-based pre-check
    if type_label == "bug":
        body = (issue.get("body") or "")
        if len(body) < 50:
            return False
        # Clear error signals → yes
        if any(sig in body.lower() for sig in ("error", "traceback", "exception", "stack trace", "```")):
            if use_llm:
                return await _llm_ai_task_judge(issue)
            return True
        # Borderline: ask LLM
        if use_llm and len(body) > 200:
            return await _llm_ai_task_judge(issue)
        return False

    # Unknown type: ask LLM
    if use_llm:
        return await _llm_ai_task_judge(issue)
    return False


async def _llm_ai_task_judge(issue: dict) -> bool:
    """Use LLM to judge if an issue is suitable for ai-task."""
    import json as json_mod
    from src.llm.client import get_light_model

    title = issue.get("title", "")
    body = (issue.get("body") or "")[:1500]

    prompt = f"""You are evaluating whether an AI coding agent can autonomously fix this GitHub issue.

Title: {title}
Body: {body}

Answer YES only if ALL conditions are true:
1. The problem is clearly defined (has specific error, repro steps, or exact behavior described)
2. The fix is likely small scope (1-3 files changed, no major architecture redesign)
3. The fix can be verified (tests exist, CI would catch regressions, or behavior is observable)

Answer NO if:
- It's a vague feature request or design discussion
- It requires human judgment on product direction
- It's a performance optimization needing profiling
- The root cause is unclear and needs investigation beyond code reading

Respond with ONLY: YES or NO"""

    model = get_light_model()
    try:
        response = await model.ainvoke(prompt)
        content = response.content.strip().upper()
        # Handle thinking models that wrap answer
        if "YES" in content and "NO" not in content:
            return True
        if "NO" in content and "YES" not in content:
            return False
        # Ambiguous → conservative NO
        return False
    except Exception as e:
        logger.warning(f"LLM ai-task judge failed for #{issue.get('number')}: {e}")
        return False


def _build_label_set(module_label, ai_task) -> list[str]:
    """Build the final set of labels to apply (only module + ai-task)."""
    labels = []
    if module_label:
        labels.append(module_label)
    if ai_task:
        labels.append("ai-task")
    return labels


async def run_scan(use_llm: bool = True):
    """Run the full Phase 1 scan."""
    if not DATA_FILE.exists():
        print(f"ERROR: {DATA_FILE} not found. Run `gh issue list` first.")
        return

    issues = json.loads(DATA_FILE.read_text())
    print(f"Loaded {len(issues)} issues from {DATA_FILE.name}")
    if use_llm:
        print("LLM mode: ON (using Haiku for ambiguous cases)\n")
    else:
        print("LLM mode: OFF (rule-based only)\n")

    results = []
    for i, issue in enumerate(issues):
        r = await classify_single(issue, use_llm=use_llm)
        results.append(r)
        mod = r["classified"]["module"] or "?"
        ai = "ai-task" if r["ai_task"] else ""
        print(f"  [{i+1:3d}/{len(issues)}] #{r['number']:4d} [{mod:6s}] {ai:7s} {r['title'][:55]}")

    # Summary statistics
    modules = {"plugin": [], "memos": [], "unknown": []}
    ai_tasks = []
    types = {}

    for r in results:
        mod = r["classified"]["module"] or "unknown"
        if mod in modules:
            modules[mod].append(r["number"])
        else:
            modules["unknown"].append(r["number"])

        t = r["classified"]["type"] or "unclassified"
        types[t] = types.get(t, 0) + 1

        if r["ai_task"]:
            ai_tasks.append(r["number"])

    print("\n" + "=" * 60)
    print("SENTINEL PHASE 1 — CLASSIFICATION REPORT")
    print("=" * 60)

    print(f"\nTotal issues scanned: {len(results)}")
    print(f"\n--- Module Distribution ---")
    print(f"  plugin : {len(modules['plugin'])} issues")
    print(f"  memos  : {len(modules['memos'])} issues")
    print(f"  unknown: {len(modules['unknown'])} issues")

    print(f"\n--- Type Distribution ---")
    for t, count in sorted(types.items(), key=lambda x: -x[1]):
        print(f"  {t:15s}: {count}")

    print(f"\n--- ai-task Candidates ({len(ai_tasks)}) ---")
    for r in results:
        if r["ai_task"]:
            mod = r["classified"]["module"] or "?"
            print(f"  #{r['number']:4d} [{mod:6s}] {r['title'][:70]}")

    print(f"\n--- Non ai-task Issues ({len(results) - len(ai_tasks)}) ---")
    for r in results:
        if not r["ai_task"]:
            mod = r["classified"]["module"] or "?"
            print(f"  #{r['number']:4d} [{mod:6s}] {r['title'][:70]}")

    # Save full report
    report = {
        "summary": {
            "total": len(results),
            "by_module": {k: len(v) for k, v in modules.items()},
            "by_type": types,
            "ai_task_count": len(ai_tasks),
            "ai_task_issues": ai_tasks,
        },
        "details": results,
    }
    REPORT_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nFull report saved to: {REPORT_FILE}")
    print("Review the report, then run `python3 -m src.phase1_apply` to apply labels.")


if __name__ == "__main__":
    use_llm = "--no-llm" not in sys.argv
    asyncio.run(run_scan(use_llm=use_llm))
