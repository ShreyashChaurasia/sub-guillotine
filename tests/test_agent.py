"""Unit tests for StrandsAgent decision making and orchestration pipeline."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch
import pytest

from src.agent.strands_agent import StrandsAgent
from src.models.schema import SubscriptionStatus
from src.storage.database import Database


@pytest.fixture
def test_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "test_agent_suite.db"
    return Database(db_path=str(db_file))


def test_agent_process_email(test_db: Database):
    """Verify agent ingests email, extracts subscription, and persists in ledger."""
    agent = StrandsAgent(db=test_db)
    email = {
        "id": "email_test_1",
        "sender": "billing@netflix.com",
        "subject": "Your Netflix Monthly Statement",
        "body_text": "Hi Alex, your Netflix Standard Plan ($15.49) will renew on August 24, 2026. Manage: http://localhost:8888/billing",
    }

    sub = agent.process_email(email)

    assert sub.id is not None
    assert "Netflix" in sub.service_name
    assert sub.amount == 15.49
    assert sub.status == SubscriptionStatus.MONITORING

    stored = test_db.get_subscription(sub.id)
    assert stored is not None
    assert stored.service_name == sub.service_name


def test_agent_pipeline_with_empty_emails(test_db: Database):
    """Verify agent handles empty email list gracefully."""
    agent = StrandsAgent(db=test_db)
    results = agent.run_guillotine_pipeline(
        emails=[],
        interactive=False,
    )

    assert results["ingested_count"] == 0
    assert results["imminent_count"] == 0
    assert results["staged_count"] == 0
    assert results["cancelled_count"] == 0
    assert results["total_saved"] == 0.0


def test_agent_pipeline_keep_decision(test_db: Database):
    """Verify agent stands down and preserves subscription when user chooses KEEP."""
    agent = StrandsAgent(db=test_db)
    simulated_now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Imminent renewal email
    email = {
        "id": "email_keep_test",
        "subject": "Upcoming SaaSPro Renewal",
        "body_text": "Your subscription ($29.00/month) will renew on August 24, 2026 at 09:00 UTC. Cancel: http://localhost:8888/billing",
    }

    # Mock stage_cancellation to avoid browser launch during unit test
    with patch("src.agent.strands_agent.stage_cancellation") as mock_stage:
        mock_stage.return_value = {
            "success": True,
            "status": "STAGED_FOR_CANCEL",
            "subscription_id": 1,
            "staged_screenshot_path": "screenshots/mock_stage.png",
            "staged_page_url": "http://localhost:8888/final-cancel",
        }

        results = agent.run_guillotine_pipeline(
            emails=[email],
            reference_time=simulated_now,
            auto_decision="KEEP",
            interactive=False,
        )

        assert results["ingested_count"] == 1
        assert results["imminent_count"] == 1
        assert results["staged_count"] == 1
        assert results["cancelled_count"] == 0
        assert results["kept_count"] == 1
        assert results["total_saved"] == 0.0

        # Verify DB status is KEPT
        subs = test_db.get_all_subscriptions()
        assert len(subs) == 1
        assert subs[0].status == SubscriptionStatus.KEPT


def test_agent_pipeline_cancel_decision(test_db: Database):
    """Verify agent commits cancellation and records savings when authorized."""
    agent = StrandsAgent(db=test_db)
    simulated_now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    email = {
        "id": "email_cancel_test",
        "subject": "Upcoming Renewal: SaaSPro Analytics",
        "body_text": "Your SaaSPro Pro Tier ($29.00/month) renews on August 24, 2026 at 09:00 UTC.",
    }

    with patch("src.agent.strands_agent.stage_cancellation") as mock_stage, \
         patch("src.agent.strands_agent.commit_cancellation") as mock_commit:

        mock_stage.return_value = {
            "success": True,
            "status": "STAGED_FOR_CANCEL",
            "subscription_id": 1,
            "staged_screenshot_path": "screenshots/mock_stage.png",
            "staged_page_url": "http://localhost:8888/final-cancel",
        }

        mock_commit.return_value = {
            "success": True,
            "status": "CANCELLED",
            "subscription_id": 1,
            "service_name": "SaaSPro Analytics",
            "amount_saved": 29.00,
            "proof_screenshot_path": "screenshots/mock_proof.png",
        }

        results = agent.run_guillotine_pipeline(
            emails=[email],
            reference_time=simulated_now,
            auto_decision="CANCEL",
            interactive=False,
        )

        assert results["ingested_count"] == 1
        assert results["imminent_count"] == 1
        assert results["staged_count"] == 1
        assert results["cancelled_count"] == 1
        assert results["kept_count"] == 0
        assert results["total_saved"] == 29.00
        assert len(results["actions"]) == 1
        assert results["actions"][0]["action"] == "CANCELLED"
