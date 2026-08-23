"""Unit tests for Pydantic models and schemas."""

from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError

from src.models.schema import (
    CancellationResult,
    ExtractedSubscriptionData,
    HITLDecision,
    HITLDecisionType,
    HITLRequest,
    ImminentSubscription,
    SubscriptionItem,
    SubscriptionStatus,
)


def test_subscription_status_enum():
    """Verify all valid lifecycle states exist in SubscriptionStatus."""
    assert SubscriptionStatus.MONITORING.value == "MONITORING"
    assert SubscriptionStatus.STAGED_FOR_CANCEL.value == "STAGED_FOR_CANCEL"
    assert SubscriptionStatus.CANCELLED.value == "CANCELLED"
    assert SubscriptionStatus.KEPT.value == "KEPT"
    assert SubscriptionStatus.FAILED.value == "FAILED"


def test_subscription_item_creation():
    """Verify SubscriptionItem creation with defaults and currency uppercasing."""
    now = datetime.now(timezone.utc)
    renewal = now + timedelta(days=3)

    sub = SubscriptionItem(
        service_name="Netflix",
        plan_name="Standard HD",
        amount=15.49,
        currency="usd",
        billing_cycle="monthly",
        renewal_date=renewal,
        cancellation_url="https://netflix.com/cancel",
    )

    assert sub.id is None
    assert sub.service_name == "Netflix"
    assert sub.plan_name == "Standard HD"
    assert sub.amount == 15.49
    assert sub.currency == "USD"
    assert sub.status == SubscriptionStatus.MONITORING
    assert sub.created_at is not None
    assert sub.updated_at is not None


def test_subscription_item_invalid_amount():
    """Verify validation error when amount is negative."""
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        SubscriptionItem(
            service_name="Test Service",
            amount=-10.0,
            renewal_date=now,
        )


def test_extracted_subscription_data_validation():
    """Verify ExtractedSubscriptionData model parsing and validation."""
    renewal = datetime(2026, 9, 1, 12, 0, 0, tzinfo=timezone.utc)
    extracted = ExtractedSubscriptionData(
        service_name="Adobe Creative Cloud",
        plan_name="All Apps",
        amount=54.99,
        currency="USD",
        billing_cycle="monthly",
        renewal_date=renewal,
        cancellation_url="https://account.adobe.com/plans",
        account_email="user@example.com",
        confidence_score=0.98,
    )

    assert extracted.service_name == "Adobe Creative Cloud"
    assert extracted.confidence_score == 0.98
    assert extracted.amount == 54.99


def test_extracted_subscription_invalid_confidence():
    """Verify confidence score must be between 0.0 and 1.0."""
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        ExtractedSubscriptionData(
            service_name="Test",
            amount=10.0,
            renewal_date=now,
            confidence_score=1.5,
        )


def test_hitl_request_and_decision():
    """Verify HITL models serialize and deserialize properly."""
    now = datetime.now(timezone.utc)
    sub = SubscriptionItem(
        id=1,
        service_name="SaaS Pro",
        amount=29.00,
        renewal_date=now + timedelta(hours=12),
    )

    req = HITLRequest(
        subscription=sub,
        hours_until_renewal=12.0,
        staged_screenshot_path="screenshots/stage_1.png",
        prompt_message="Renewal imminent. Approve cancellation?",
    )

    assert req.subscription.id == 1
    assert req.hours_until_renewal == 12.0

    decision = HITLDecision(
        decision=HITLDecisionType.CANCEL,
        subscription_id=1,
        reason="No longer using this tool",
    )

    assert decision.decision == HITLDecisionType.CANCEL
    assert decision.subscription_id == 1


def test_cancellation_result():
    """Verify CancellationResult model."""
    result = CancellationResult(
        success=True,
        subscription_id=1,
        service_name="SaaS Pro",
        amount_saved=29.00,
        proof_screenshot_path="screenshots/proof_1.png",
    )

    assert result.success is True
    assert result.amount_saved == 29.00
    assert result.currency == "USD"
