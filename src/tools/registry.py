"""Tool registry — collects all tools for the LangGraph agent."""

from __future__ import annotations

from src.tools.github_read import (
    read_issue,
    read_pr,
    read_file,
    search_issues,
    search_code,
    list_pr_checks,
    get_pr_reviews,
    list_open_issues,
    list_open_prs,
)
from src.tools.github_write import (
    add_labels,
    remove_labels,
    post_comment,
    submit_review,
    close_issue,
    close_pr,
)
from src.tools.github_dev import (
    clone_repo,
    create_branch,
    edit_file,
    commit_and_push,
    create_pull_request,
    trigger_ci,
)

MANAGEMENT_TOOLS_READ = [
    read_issue,
    read_pr,
    read_file,
    search_issues,
    search_code,
    list_pr_checks,
    get_pr_reviews,
    list_open_issues,
    list_open_prs,
]

MANAGEMENT_TOOLS_WRITE = [
    add_labels,
    remove_labels,
    post_comment,
    submit_review,
    close_issue,
    close_pr,
]

DEV_TOOLS = [
    clone_repo,
    create_branch,
    edit_file,
    commit_and_push,
    create_pull_request,
    trigger_ci,
]

ALL_TOOLS = MANAGEMENT_TOOLS_READ + MANAGEMENT_TOOLS_WRITE + DEV_TOOLS

DANGEROUS_TOOLS = {"close_issue", "close_pr", "submit_review"}


def get_tools_for_complexity(complexity: str) -> list:
    """Return the tool set available for a given complexity level."""
    match complexity:
        case "fast":
            return MANAGEMENT_TOOLS_READ + [add_labels, remove_labels]
        case "light":
            return MANAGEMENT_TOOLS_READ + MANAGEMENT_TOOLS_WRITE
        case "full":
            return MANAGEMENT_TOOLS_READ + MANAGEMENT_TOOLS_WRITE
        case "dev":
            return ALL_TOOLS
        case _:
            return MANAGEMENT_TOOLS_READ
