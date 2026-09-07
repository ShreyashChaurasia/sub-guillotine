"""Unit tests for the 5 Sub Guillotine Strands Tools."""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from src.models.schema import SubscriptionItem, SubscriptionStatus
from src.storage.database import Database
from src.tools.browser_canceler import stage_cancellation
from src.tools.deadline_tracker import check_imminent_deadlines
from src.tools.email_extractor import extract_subscription_from_email
from src.tools.hitl_notifier import _send_telegram_notification, dispatch_hitl_decision
from src.main import print_banner, show_ledger_status


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


def test_email_extractor_eur_currency():
    """Test extracting subscription in EUR currency."""
    sample_text = "Your subscription fee of EUR 49.99 will be charged on September 15, 2026."
    result = extract_subscription_from_email(sample_text, "CloudVault Billing")

    assert result["amount"] == 49.99
    assert result["currency"] == "EUR"


def test_email_extractor_html_format():
    """Test extracting from HTML formatted email body."""
    html = "<p>Your GymPass Premium ($79.00 USD) will renew on September 15, 2026 at https://gympass.mock/memberships/cancel</p>"
    result = extract_subscription_from_email(html, "GymPass Renewal")

    assert "GymPass" in result["service_name"]
    assert result["amount"] == 79.00
    assert result["currency"] == "USD"


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


def test_deadline_tracker_excludes_non_monitoring(temp_db: Database):
    """Verify check_imminent_deadlines ignores cancelled or kept subscriptions."""
    ref_time = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    temp_db.add_subscription(
        SubscriptionItem(
            service_name="Cancelled Sub",
            amount=20.00,
            renewal_date=ref_time + timedelta(hours=5),
            status=SubscriptionStatus.CANCELLED,
        )
    )
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="Kept Sub",
            amount=30.00,
            renewal_date=ref_time + timedelta(hours=5),
            status=SubscriptionStatus.KEPT,
        )
    )

    result = check_imminent_deadlines(
        threshold_hours=24,
        reference_time_iso=ref_time.isoformat(),
        db_path=temp_db.db_path,
    )

    assert result["imminent_count"] == 0
    assert result["potential_savings"] == 0.0


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
        subscription_id=sub.id,
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
        subscription_id=sub.id,
        service_name=sub.service_name,
        amount=sub.amount,
        hours_remaining=5.0,
        interactive=False,
        auto_decision="KEEP",
        db_path=temp_db.db_path,
    )

    assert decision["decision"] == "KEEP"
    updated_sub = temp_db.get_subscription(sub.id)
    assert updated_sub is not None
    assert updated_sub.status == SubscriptionStatus.KEPT


def test_hitl_decision_defer(temp_db: Database):
    """Test dispatch_hitl_decision tool with unknown/defer input."""
    sub = temp_db.add_subscription(
        SubscriptionItem(
            service_name="Deferred Sub",
            amount=25.00,
            renewal_date=datetime.now(timezone.utc) + timedelta(hours=5),
        )
    )

    decision = dispatch_hitl_decision(
        subscription_id=sub.id,
        service_name=sub.service_name,
        amount=sub.amount,
        hours_remaining=5.0,
        interactive=False,
        auto_decision="LATER",
        db_path=temp_db.db_path,
    )

    assert decision["decision"] == "DEFER"


def test_telegram_notification_text_success():
    """Verify Telegram text alert dispatch when no screenshot provided."""
    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)

        success = _send_telegram_notification(
            bot_token="test_token_123",
            chat_id="test_chat_456",
            subscription_id=10,
            service_name="CloudVault",
            amount=9.99,
            currency="USD",
            hours_remaining=12.0,
            staged_screenshot_path=None,
        )

        assert success is True
        assert mock_post.called
        call_args = mock_post.call_args
        assert "sendMessage" in call_args[0][0]


def test_telegram_notification_photo_success(tmp_path: Path):
    """Verify Telegram photo alert dispatch when screenshot exists."""
    screenshot = tmp_path / "test_stage.png"
    screenshot.write_bytes(b"mock_png_data")

    with patch("httpx.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200)

        success = _send_telegram_notification(
            bot_token="test_token_123",
            chat_id="test_chat_456",
            subscription_id=10,
            service_name="CloudVault",
            amount=9.99,
            currency="USD",
            hours_remaining=12.0,
            staged_screenshot_path=str(screenshot),
        )

        assert success is True
        assert mock_post.called
        call_args = mock_post.call_args
        assert "sendPhoto" in call_args[0][0]


def test_telegram_notification_failure():
    """Verify Telegram failure handling does not raise exceptions."""
    with patch("httpx.post", side_effect=Exception("Network down")):
        success = _send_telegram_notification(
            bot_token="invalid",
            chat_id="invalid",
            subscription_id=1,
            service_name="Test",
            amount=10.0,
            currency="USD",
            hours_remaining=1.0,
        )
        assert success is False


def test_main_cli_helpers(temp_db: Database):
    """Verify main.py banner and ledger status renderer."""
    print_banner()
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="Ledger Sub",
            amount=19.99,
            renewal_date=datetime.now(timezone.utc),
        )
    )
    show_ledger_status(temp_db.db_path)


def test_stage_cancellation_invalid_url(temp_db: Database):
    """Test stage_cancellation returns graceful failure on invalid URL."""
    sub = temp_db.add_subscription(
        SubscriptionItem(
            service_name="Broken URL Sub",
            amount=12.00,
            renewal_date=datetime.now(timezone.utc) + timedelta(hours=4),
        )
    )

    result = stage_cancellation(
        target_url="http://invalid.nonexistent.domain:9999/nowhere",
        subscription_id=sub.id,
        db_path=temp_db.db_path,
    )

    assert result["success"] is False
    assert result["status"] == "ERROR"
    assert "error" in result
