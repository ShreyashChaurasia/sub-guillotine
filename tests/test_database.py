"""Unit tests for SQLite database manager and CRUD operations."""

from datetime import datetime, timezone, timedelta
from pathlib import Path
import pytest

from src.models.schema import SubscriptionItem, SubscriptionStatus
from src.storage.database import Database


@pytest.fixture
def temp_db(tmp_path: Path) -> Database:
    """Fixture to provide an isolated test database in tmp_path."""
    db_file = tmp_path / "test_sub_guillotine.db"
    return Database(db_path=str(db_file))


def test_db_init_and_add_subscription(temp_db: Database):
    """Test adding a subscription to the database."""
    now = datetime.now(timezone.utc)
    renewal = now + timedelta(days=7)

    item = SubscriptionItem(
        service_name="Spotify Premium",
        plan_name="Individual",
        amount=10.99,
        currency="USD",
        billing_cycle="monthly",
        renewal_date=renewal,
        cancellation_url="https://spotify.com/account",
    )

    created = temp_db.add_subscription(item)

    assert created is not None
    assert created.id is not None
    assert created.service_name == "Spotify Premium"
    assert created.amount == 10.99
    assert created.status == SubscriptionStatus.MONITORING


def test_get_subscription(temp_db: Database):
    """Test fetching a subscription by ID."""
    now = datetime.now(timezone.utc)
    item = SubscriptionItem(
        service_name="GitHub Copilot",
        amount=10.00,
        renewal_date=now + timedelta(days=14),
    )
    created = temp_db.add_subscription(item)

    fetched = temp_db.get_subscription(created.id)  # type: ignore
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.service_name == "GitHub Copilot"

    missing = temp_db.get_subscription(99999)
    assert missing is None


def test_get_all_subscriptions_and_by_status(temp_db: Database):
    """Test querying all subscriptions and filtering by status."""
    now = datetime.now(timezone.utc)
    sub1 = SubscriptionItem(
        service_name="Sub A",
        amount=5.00,
        renewal_date=now + timedelta(days=1),
        status=SubscriptionStatus.MONITORING,
    )
    sub2 = SubscriptionItem(
        service_name="Sub B",
        amount=15.00,
        renewal_date=now + timedelta(days=2),
        status=SubscriptionStatus.CANCELLED,
    )
    temp_db.add_subscription(sub1)
    temp_db.add_subscription(sub2)

    all_subs = temp_db.get_all_subscriptions()
    assert len(all_subs) == 2

    monitoring = temp_db.get_subscriptions_by_status(SubscriptionStatus.MONITORING)
    assert len(monitoring) == 1
    assert monitoring[0].service_name == "Sub A"

    cancelled = temp_db.get_subscriptions_by_status(SubscriptionStatus.CANCELLED)
    assert len(cancelled) == 1
    assert cancelled[0].service_name == "Sub B"


def test_imminent_deadline_detection(temp_db: Database):
    """Test detecting subscriptions renewing within a threshold."""
    ref_time = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Imminent within 24h (10 hours away)
    sub_imminent = SubscriptionItem(
        service_name="Expiring Soon",
        amount=25.00,
        renewal_date=ref_time + timedelta(hours=10),
    )
    # Critical (4 hours away)
    sub_critical = SubscriptionItem(
        service_name="Expiring Critical",
        amount=30.00,
        renewal_date=ref_time + timedelta(hours=4),
    )
    # Safe (>24h away, 48 hours)
    sub_safe = SubscriptionItem(
        service_name="Expiring Later",
        amount=50.00,
        renewal_date=ref_time + timedelta(hours=48),
    )
    # Already expired / in the past
    sub_past = SubscriptionItem(
        service_name="Already Passed",
        amount=10.00,
        renewal_date=ref_time - timedelta(hours=2),
    )

    temp_db.add_subscription(sub_imminent)
    temp_db.add_subscription(sub_critical)
    temp_db.add_subscription(sub_safe)
    temp_db.add_subscription(sub_past)

    imminent_list = temp_db.get_imminent_subscriptions(
        threshold_hours=24,
        reference_time=ref_time,
    )

    assert len(imminent_list) == 2
    # Should be sorted ascending by hours_remaining
    assert imminent_list[0].subscription.service_name == "Expiring Critical"
    assert imminent_list[0].is_critical is True
    assert imminent_list[0].hours_remaining == 4.0

    assert imminent_list[1].subscription.service_name == "Expiring Soon"
    assert imminent_list[1].is_critical is False
    assert imminent_list[1].hours_remaining == 10.0


def test_update_status_and_screenshots(temp_db: Database):
    """Test updating lifecycle state machine and screenshot paths."""
    now = datetime.now(timezone.utc)
    item = SubscriptionItem(
        service_name="Test Sub",
        amount=20.00,
        renewal_date=now + timedelta(days=1),
    )
    created = temp_db.add_subscription(item)
    sub_id = created.id  # type: ignore

    # Stage for cancel
    staged = temp_db.update_status(
        sub_id=sub_id,
        status=SubscriptionStatus.STAGED_FOR_CANCEL,
        pre_cancel_screenshot_path="screenshots/stage_test.png",
    )
    assert staged is not None
    assert staged.status == SubscriptionStatus.STAGED_FOR_CANCEL
    assert staged.pre_cancel_screenshot_path == "screenshots/stage_test.png"

    # Confirm cancel
    cancelled = temp_db.update_status(
        sub_id=sub_id,
        status=SubscriptionStatus.CANCELLED,
        proof_screenshot_path="screenshots/proof_test.png",
    )
    assert cancelled is not None
    assert cancelled.status == SubscriptionStatus.CANCELLED
    assert cancelled.proof_screenshot_path == "screenshots/proof_test.png"
    assert cancelled.pre_cancel_screenshot_path == "screenshots/stage_test.png"


def test_savings_calculation(temp_db: Database):
    """Test calculating total money saved."""
    now = datetime.now(timezone.utc)

    # Cancelled subs
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="SaaS A",
            amount=29.99,
            renewal_date=now,
            status=SubscriptionStatus.CANCELLED,
        )
    )
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="SaaS B",
            amount=49.00,
            renewal_date=now,
            status=SubscriptionStatus.CANCELLED,
        )
    )
    # Kept/Monitoring subs
    temp_db.add_subscription(
        SubscriptionItem(
            service_name="SaaS C",
            amount=100.00,
            renewal_date=now,
            status=SubscriptionStatus.KEPT,
        )
    )

    savings = temp_db.get_total_savings()
    assert round(savings, 2) == 78.99


def test_delete_subscription(temp_db: Database):
    """Test deleting a subscription record."""
    now = datetime.now(timezone.utc)
    item = temp_db.add_subscription(
        SubscriptionItem(service_name="To Delete", amount=5.00, renewal_date=now)
    )
    assert temp_db.delete_subscription(item.id) is True  # type: ignore
    assert temp_db.get_subscription(item.id) is None  # type: ignore
    assert temp_db.delete_subscription(item.id) is False  # type: ignore


def test_upsert_updates_existing_subscription(temp_db: Database):
    """Test that adding a subscription with the same service name updates the record rather than creating a duplicate."""
    now = datetime.now(timezone.utc)
    sub1 = SubscriptionItem(
        service_name="CloudStorage Inc",
        amount=10.00,
        renewal_date=now + timedelta(days=5),
        cancellation_url="http://example.com/cancel1",
    )
    first_saved = temp_db.add_subscription(sub1)
    assert first_saved is not None
    assert first_saved.id is not None

    # Add same service name with updated amount and url
    sub2 = SubscriptionItem(
        service_name="CloudStorage Inc",
        amount=12.50,
        renewal_date=now + timedelta(days=30),
        cancellation_url="http://example.com/cancel2",
    )
    second_saved = temp_db.add_subscription(sub2)
    assert second_saved is not None
    assert second_saved.id == first_saved.id
    assert second_saved.amount == 12.50
    assert second_saved.cancellation_url == "http://example.com/cancel2"

    # Ledger should still only have 1 row
    all_subs = temp_db.get_all_subscriptions()
    assert len(all_subs) == 1


def test_upsert_preserves_cancelled_status(temp_db: Database):
    """Test that incoming emails for an already CANCELLED subscription do not revert it to MONITORING."""
    now = datetime.now(timezone.utc)
    sub = SubscriptionItem(
        service_name="SaaSPro Tool",
        amount=29.00,
        renewal_date=now + timedelta(days=1),
    )
    saved = temp_db.add_subscription(sub)
    temp_db.update_status(saved.id, SubscriptionStatus.CANCELLED)  # type: ignore

    # Simulate re-running with the same email
    re_added = temp_db.add_subscription(sub)
    assert re_added.id == saved.id
    assert re_added.status == SubscriptionStatus.CANCELLED

    # Check that savings are maintained
    assert temp_db.get_total_savings() == 29.00


def test_get_subscription_by_service_case_insensitive(temp_db: Database):
    """Test querying subscription by service name with case-insensitivity."""
    now = datetime.now(timezone.utc)
    sub = SubscriptionItem(
        service_name="Netflix Standard",
        amount=15.49,
        renewal_date=now + timedelta(days=10),
    )
    saved = temp_db.add_subscription(sub)

    found = temp_db.get_subscription_by_service("netflix standard")
    assert found is not None
    assert found.id == saved.id
    assert found.service_name == "Netflix Standard"

    found_upper = temp_db.get_subscription_by_service("  NETFLIX STANDARD  ")
    assert found_upper is not None
    assert found_upper.id == saved.id
