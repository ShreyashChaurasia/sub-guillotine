"""End-to-End integration test for Sub Guillotine full autonomous pipeline."""

import multiprocessing
import time
from datetime import datetime, timezone
from pathlib import Path
import pytest

from src.agent.strands_agent import StrandsAgent
from src.config import Settings
from src.mock_services.mock_saas_portal import run_server
from src.models.schema import SubscriptionStatus
from src.storage.database import Database


@pytest.fixture(scope="module")
def mock_server_port():
    """Start mock SaaS portal on port 8899 in a background process."""
    port = 8899
    process = multiprocessing.Process(
        target=run_server,
        kwargs={"host": "127.0.0.1", "port": port},
        daemon=True,
    )
    process.start()
    time.sleep(1.2)  # Allow server to bind
    yield port
    if process.is_alive():
        process.terminate()
        process.join(timeout=1.0)


def test_full_cancellation_e2e_pipeline(tmp_path: Path, mock_server_port: int):
    """Test full 5-phase pipeline from email to proof screenshot."""
    db_file = tmp_path / "e2e_test.db"
    screenshots_folder = tmp_path / "screenshots"
    screenshots_folder.mkdir(parents=True, exist_ok=True)

    db = Database(db_path=str(db_file))
    agent = StrandsAgent(db=db)

    # Mock email pointing to the running test server
    sample_email = {
        "id": "email_e2e_001",
        "sender": "billing@saaspro.mock",
        "subject": "Upcoming Renewal Notice: SaaSPro Analytics",
        "body_text": f"Your SaaSPro Pro Tier ($29.00/month) will renew on August 24, 2026 at 09:00 UTC. Cancel at: http://127.0.0.1:{mock_server_port}/billing",
    }

    # Reference time simulated at August 23, 2026 12:00 UTC (renewal is 21 hours away)
    simulated_now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

    # Run pipeline with auto-decision = CANCEL
    results = agent.run_guillotine_pipeline(
        emails=[sample_email],
        reference_time=simulated_now,
        auto_decision="CANCEL",
        interactive=False,
    )

    assert results["ingested_count"] == 1
    assert results["imminent_count"] == 1
    assert results["staged_count"] == 1
    assert results["cancelled_count"] == 1
    assert results["total_saved"] == 29.00

    # Verify Database state
    subs = db.get_all_subscriptions()
    assert len(subs) == 1
    sub = subs[0]
    assert sub.service_name == "SaaSPro Analytics"
    assert sub.status == SubscriptionStatus.CANCELLED
    assert sub.proof_screenshot_path is not None
    assert Path(sub.proof_screenshot_path).exists()
    assert sub.pre_cancel_screenshot_path is not None
    assert Path(sub.pre_cancel_screenshot_path).exists()
