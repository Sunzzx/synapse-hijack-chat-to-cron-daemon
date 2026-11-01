"""
Tests for synapse-hijack-chat-to-cron-daemon
"""

import json
import tempfile
from pathlib import Path
import pytest

from synapse_hijack.intent_extractor import IntentExtractor, IntentKind
from synapse_hijack.self_healing_engine import SelfHealingEngine, StrategyKind
from synapse_hijack.cron_bridge import CronBridge, CronJobDefinition


def test_intent_extractor_basic():
    extractor = IntentExtractor()
    chat = """
    Can you clean hermes deadcode and stubs please?
    Also fix quota_failover when you have a minute.
    Build a repo called hyper-cache every 30m.
    """
    intents = extractor.parse(chat)
    assert len(intents) >= 3

    kinds = {i.kind for i in intents}
    assert IntentKind.SYSTEM_PRUNE in kinds
    assert IntentKind.BUG_HEAL in kinds
    assert IntentKind.PROJECT_ARCHITECT in kinds

    # Verify crazy repo naming suggestion
    architect_intent = next(i for i in intents if i.kind == IntentKind.PROJECT_ARCHITECT)
    assert architect_intent.suggested_repo_name is not None
    assert "synapse" in architect_intent.suggested_repo_name or "daemon" in architect_intent.suggested_repo_name


def test_self_healing_engine_success():
    engine = SelfHealingEngine(timeout_per_strategy=5)
    res = engine.execute_command("echo 'Autonomous Test Passed'")
    assert res.overall_success is True
    assert res.final_strategy == StrategyKind.STRATEGY_DIRECT_EXECUTION
    assert "Autonomous Test Passed" in res.output
    assert len(res.attempts) == 1


def test_self_healing_engine_fallback_repair():
    engine = SelfHealingEngine(timeout_per_strategy=5)
    # A command that fails in strategy 1 and 2, but has a patch function that fixes it for strategy 3
    def mock_patch(out, err):
        return "Applied dynamic fix"

    res = engine.execute_command(
        "exit 1",
        patch_fn=mock_patch,
    )
    # Verify that all 3 strategies were attempted
    assert len(res.attempts) == 3
    assert res.attempts[0].strategy == StrategyKind.STRATEGY_DIRECT_EXECUTION
    assert res.attempts[1].strategy == StrategyKind.STRATEGY_ISOLATED_SANDBOX
    assert res.attempts[2].strategy == StrategyKind.STRATEGY_FALLBACK_REPAIR


def test_cron_bridge_upsert_and_delete():
    with tempfile.TemporaryDirectory() as tmpdir:
        fake_jobs_file = Path(tmpdir) / "jobs.json"
        bridge = CronBridge(fake_jobs_file)

        # Initial load
        assert bridge.load_jobs() == []

        # Upsert
        job = CronJobDefinition(
            name="test-synapse-job",
            prompt="Run automated self-check",
            schedule_display="every 15m",
            minutes=15,
            no_agent=True,
        )
        assert bridge.upsert_job(job) is True

        jobs = bridge.load_jobs()
        assert len(jobs) == 1
        assert jobs[0]["name"] == "test-synapse-job"
        assert jobs[0]["no_agent"] is True

        # Update existing
        job.minutes = 30
        job.schedule_display = "every 30m"
        assert bridge.upsert_job(job) is True
        jobs_updated = bridge.load_jobs()
        assert len(jobs_updated) == 1
        assert jobs_updated[0]["schedule"]["minutes"] == 30

        # Delete
        assert bridge.delete_job("test-synapse-job") is True
        assert bridge.load_jobs() == []
