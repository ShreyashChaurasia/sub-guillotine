"""Deadline tracker tool for monitoring upcoming renewal expirations."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.config import get_settings
from src.models.schema import ImminentSubscription
from src.storage.database import get_db


def check_imminent_deadlines(
    threshold_hours: Optional[int] = None,
    reference_time_iso: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strands Tool: Checks the SQLite ledger for subscriptions with imminent renewal deadlines.
    Identifies subscriptions expiring within threshold_hours (default: 24h).
    """
    settings = get_settings()
    hours = threshold_hours if threshold_hours is not None else settings.deadline_threshold_hours
    db = get_db(db_path)

    ref_time = None
    if reference_time_iso:
        ref_time = datetime.fromisoformat(reference_time_iso)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)
    else:
        ref_time = datetime.now(timezone.utc)

    imminent_list: List[ImminentSubscription] = db.get_imminent_subscriptions(
        threshold_hours=hours,
        reference_time=ref_time,
    )

    imminent_dicts = [item.model_dump(mode="json") for item in imminent_list]
    total_potential_savings = sum(item.subscription.amount for item in imminent_list)

    return {
        "imminent_count": len(imminent_list),
        "threshold_hours": hours,
        "reference_time": ref_time.isoformat(),
        "imminent_subscriptions": imminent_dicts,
        "potential_savings": round(total_potential_savings, 2),
    }
