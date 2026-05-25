"""Tests for the router module."""

import pytest

from src.agent.router import classify_complexity


class TestClassifyComplexity:
    def test_ai_task_label_returns_dev(self):
        event = {
            "type": "issues",
            "action": "labeled",
            "payload": {"label": {"name": "ai-task"}, "issue": {"number": 1}},
        }
        assert classify_complexity(event) == "dev"

    def test_pr_opened_returns_full(self):
        event = {
            "type": "pull_request",
            "action": "opened",
            "payload": {"pull_request": {"number": 1}},
        }
        assert classify_complexity(event) == "full"

    def test_issue_opened_returns_light(self):
        event = {
            "type": "issues",
            "action": "opened",
            "payload": {"issue": {"number": 1}},
        }
        assert classify_complexity(event) == "light"

    def test_issue_closed_returns_fast(self):
        event = {
            "type": "issues",
            "action": "closed",
            "payload": {"issue": {"number": 1}},
        }
        assert classify_complexity(event) == "fast"

    def test_unknown_event_returns_light(self):
        event = {"type": "ping", "action": "", "payload": {}}
        assert classify_complexity(event) == "light"


class TestDuplicateDetection:
    def test_extract_keywords(self):
        from src.agent.duplicate_detector import _extract_keywords

        keywords = _extract_keywords("How to fix the memory leak in scheduler")
        assert "memory" in keywords
        assert "leak" in keywords
        assert "scheduler" in keywords
        assert "the" not in keywords
        assert "to" not in keywords


class TestLabelClassifier:
    def test_classify_type_bug(self):
        from src.labels.classifier import _classify_type

        assert _classify_type("fix crash on startup") == "bug"

    def test_classify_type_enhancement(self):
        from src.labels.classifier import _classify_type

        assert _classify_type("add support for new model") == "enhancement"

    def test_classify_module_plugin(self):
        from src.labels.classifier import _classify_module

        assert _classify_module("plugin bridge not working") == "mod:plugin"

    def test_classify_module_memos(self):
        from src.labels.classifier import _classify_module

        assert _classify_module("memory recall broken") == "mod:memos"

    def test_classify_module_infra(self):
        from src.labels.classifier import _classify_module

        assert _classify_module("docker build failing") == "mod:infra"

    def test_classify_priority_critical(self):
        from src.labels.classifier import _classify_priority

        assert _classify_priority("crash data loss", "regression", "mod:memos") == "P0:critical"

    def test_classify_priority_normal_default(self):
        from src.labels.classifier import _classify_priority

        assert _classify_priority("something minor", "enhancement", "mod:infra") == "P2:normal"
