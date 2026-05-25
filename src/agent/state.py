"""AgentState definition for LangGraph orchestrator."""

from __future__ import annotations

from functools import lru_cache
from typing import TypedDict

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    langsmith_api_key: str = ""
    langsmith_project: str = "memos-sentinel"

    github_app_id: str = ""
    github_app_private_key_path: str = "./keys/github-app.pem"
    github_webhook_secret: str = ""
    github_target_repo: str = "MemTensor/MemOS"

    dingtalk_webhook_url: str = ""
    dingtalk_secret: str = ""

    web_base_url: str = "http://localhost:8000"
    web_secret_key: str = "change-me"

    database_url: str = "sqlite+aiosqlite:///./data/sentinel.db"

    dry_run: bool = True
    max_dev_retries: int = 2
    concurrency_limit: int = 3

    # Merge strategy
    merge_method: str = "squash"  # squash | merge | rebase
    auto_delete_branch: bool = True
    require_ci_pass: bool = True
    require_approval_count: int = 1

    # Base branch strategy
    default_base_branch: str = "main"
    dev_branch_prefix: str = "autodev/sentinel-"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()


class DevContext(TypedDict, total=False):
    """Context for ai-task development flow."""

    issue_number: int
    branch_name: str
    files_modified: list[str]
    pr_number: int | None
    ci_attempts: int
    clone_path: str


class AgentState(TypedDict, total=False):
    """LangGraph state for the orchestrator agent."""

    event: dict
    complexity: str  # "fast" | "light" | "full" | "dev"
    labels_to_add: list[str]
    labels_to_remove: list[str]
    messages: list
    actions_taken: list[dict]
    pending_approval: dict | None
    dev_context: DevContext | None
    final_summary: str
    error: str | None
    retry_count: int
    lock_key: str | None
