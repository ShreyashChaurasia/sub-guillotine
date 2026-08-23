"""Unit tests for the 5 Sub Guillotine Strands Tools."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.models.schema import SubscriptionItem, SubscriptionStatus
from src.storage.database import Database
from src.tools.deadline_tracker import check_imminent_deadlines
from src.tools.email_extractor import extract_subscription_from_email
from src.tools.hitl_notifier import dispatch_hitl_decision


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    db_file = tmp_path / "tools_test.db"
    return Database(db_path=str(db_file))


def test_email_extractor_saaspro():
    """Test extracting subscription from SaaSPro sample email."""
    sample_text = """
    Hi Alex,
    Your monthly subscription to SaaSPro Analytics Pro Tier ($29.00/month) will automatically renew on August 24, 2026 at 09:00 UTC.
    To manage or cancel: http://localhost:8888/billing
    """
    result = extract_subscription_from_email(sample_text, "Upcoming Renewal: SaaSPro")

    assert "SaaSPro" in result["service_name"]
    assert result["amount"] == 29.00
    assert result["currency"] == "USD"
    assert "http://localhost:8888/billing" in result["cancellation_url"]


def test_email_extractor_adobe():
    """Test extracting subscription from Adobe sample email."""
    sample_text = """
    Dear Alex Chen,
    Your annual subscription for Adobe Creative Cloud All Apps will renew on August 28, 2026 for $54.99 USD.
    Cancel anytime: https://account.adobe.com/plans/cancel
    """
    result = extract_subscription_from_email(sample_text, "Your Adobe subscription")

    assert "Adobe" in result["service_name"]
    assert result["amount"] == 54.99
    assert result["currency"] == "USD"
    assert "https://account.adobe.com/plans/cancel" in result["cancellation_url"]


def test_deadline_tracker_tool(temp_db: Database):
    """Test check_imminent_deadlines tool."""
    ref_time = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)
    
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="Urgent Sub",
            amount=45.00,
            renewal_date=ref_time + timedelta(hours=8),
        )
    )
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="Distant Sub",
            amount=100.00,
            renewal_date=ref_time + timedelta(days=5),
        )
    )

    tracker_result = check_imminent_deadlines(
        threshold_hours=24,
        reference_time_iso=ref_time.isoformat(),
        db_path=temp_db.db_path,
    )

    assert tracker_result["imminent_count"] == 1
    assert tracker_result["potential_savings"] == 45.00
    assert len(tracker_result["imminent_subscriptions"]) == 1
    assert tracker_result["imminent_subscriptions"][0]["subscription"]["service_name"] == "Urgent Sub"


def test_hitl_decision_tool_cancel(temp_db: Database):
    """Test dispatch_hitl_decision tool with CANCEL authorization."""
    sub = temp_db.add_subscription(
        SubscriptionItem(
            service_name="Auto Sub",
            amount=30.00,
            renewal_date=datetime.now(timezone.utc) + timedelta(hours=5),
        )
    )

    decision = dispatch_hitl_decision(
        subscription_id=sub.id,  # type: ignore
        service_name=sub.service_name,
        amount=sub.amount,
        hours_remaining=5.0,
        interactive=False,
        auto_decision="CANCEL",
        db_path=temp_db.db_path,
    )

    assert decision["decision"] == "CANCEL"
    assert decision["subscription_id"] == sub.id


def test_hitl_decision_tool_keep(temp_db: Database):
    """Test dispatch_hitl_decision tool with KEEP decision updating DB."""
    sub = temp_db.add_subscription(
        SubscriptionItem(
            service_name="Retained Sub",
            amount=15.00,
            renewal_date=datetime.now(timezone.utc) + timedelta(hours=5),
        )
    )

    decision = dispatch_hitl_decision(
        subscription_id=sub.id,  # type: ignore
        service_name=sub.service_name,
        amount=sub.amount,
        hours_remaining=5.0,
        interactive=False,
        auto_decision="KEEP",
        db_path=temp_db.db_path,
    )

    assert decision["decision"] == "KEEP"
    updated_sub = temp_db.get_subscription(sub.id)  # type: ignore
    assert updated_sub is not None
    assert updated_sub.status == SubscriptionStatus.KEPT
