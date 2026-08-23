"""SQLite storage and ledger management for Sub Guillotine."""

import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

from src.config import get_settings
from src.models.schema import (
    ImminentSubscription,
    SubscriptionItem,
    SubscriptionStatus,
)


class Database:
    """SQLite database manager for tracking subscriptions and state transitions."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or get_settings().database_path
        self._ensure_db_dir()
        self.init_db()

    def _ensure_db_dir(self) -> None:
        """Ensure the parent directory for the SQLite file exists."""
        db_file = Path(self.db_path)
        if db_file.parent and str(db_file.parent) != ".":
            db_file.parent.mkdir(parents=True, exist_ok=True)

    def _get_connection(self) -> sqlite3.Connection:
        """Create a sqlite3 connection with Row factory enabled."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def init_db(self) -> None:
        """Create database tables and indices if they do not exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_name TEXT NOT NULL,
                    plan_name TEXT,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL DEFAULT 'USD',
                    billing_cycle TEXT NOT NULL DEFAULT 'monthly',
                    renewal_date TEXT NOT NULL,
                    cancellation_url TEXT,
                    login_url TEXT,
                    status TEXT NOT NULL DEFAULT 'MONITORING',
                    proof_screenshot_path TEXT,
                    pre_cancel_screenshot_path TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_subscriptions_status
                ON subscriptions(status);
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_subscriptions_renewal
                ON subscriptions(renewal_date);
                """
            )
            conn.commit()

    def add_subscription(self, sub: SubscriptionItem) -> SubscriptionItem:
        """Insert a new subscription into the ledger."""
        now_str = datetime.now(timezone.utc).isoformat()
        renewal_iso = sub.renewal_date.isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO subscriptions (
                    service_name,
                    plan_name,
                    amount,
                    currency,
                    billing_cycle,
                    renewal_date,
                    cancellation_url,
                    login_url,
                    status,
                    proof_screenshot_path,
                    pre_cancel_screenshot_path,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    sub.service_name,
                    sub.plan_name,
                    sub.amount,
                    sub.currency,
                    sub.billing_cycle,
                    renewal_iso,
                    sub.cancellation_url,
                    sub.login_url,
                    sub.status.value,
                    sub.proof_screenshot_path,
                    sub.pre_cancel_screenshot_path,
                    now_str,
                    now_str,
                ),
            )
            sub_id = cursor.lastrowid
            conn.commit()

        return self.get_subscription(sub_id)  # type: ignore

    def get_subscription(self, sub_id: int) -> Optional[SubscriptionItem]:
        """Fetch a single subscription by primary key ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscriptions WHERE id = ?;", (sub_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def get_all_subscriptions(self) -> List[SubscriptionItem]:
        """Fetch all subscriptions in the ledger."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM subscriptions ORDER BY renewal_date ASC;")
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_subscriptions_by_status(self, status: SubscriptionStatus) -> List[SubscriptionItem]:
        """Fetch subscriptions filtering by status."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM subscriptions WHERE status = ? ORDER BY renewal_date ASC;",
                (status.value,),
            )
            rows = cursor.fetchall()
            return [self._row_to_model(row) for row in rows]

    def get_imminent_subscriptions(
        self,
        threshold_hours: int = 24,
        reference_time: Optional[datetime] = None,
    ) -> List[ImminentSubscription]:
        """
        Identify subscriptions renewing within the given threshold (in hours).
        Filters for items in MONITORING status.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        deadline_limit = ref_time + timedelta(hours=threshold_hours)

        monitoring_subs = self.get_subscriptions_by_status(SubscriptionStatus.MONITORING)
        imminent = []

        for sub in monitoring_subs:
            sub_renewal = sub.renewal_date
            if sub_renewal.tzinfo is None:
                sub_renewal = sub_renewal.replace(tzinfo=timezone.utc)

            # Check if renewal is upcoming within threshold (between now and deadline)
            if ref_time <= sub_renewal <= deadline_limit:
                diff_seconds = (sub_renewal - ref_time).total_seconds()
                hours_remaining = max(0.0, diff_seconds / 3600.0)
                is_critical = hours_remaining <= 6.0
                imminent.append(
                    ImminentSubscription(
                        subscription=sub,
                        hours_remaining=round(hours_remaining, 2),
                        is_critical=is_critical,
                    )
                )

        imminent.sort(key=lambda x: x.hours_remaining)
        return imminent

    def update_status(
        self,
        sub_id: int,
        status: SubscriptionStatus,
        proof_screenshot_path: Optional[str] = None,
        pre_cancel_screenshot_path: Optional[str] = None,
    ) -> Optional[SubscriptionItem]:
        """Update subscription state and optional screenshot attachments."""
        now_str = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            updates = ["status = ?", "updated_at = ?"]
            params: list = [status.value, now_str]

            if proof_screenshot_path is not None:
                updates.append("proof_screenshot_path = ?")
                params.append(proof_screenshot_path)

            if pre_cancel_screenshot_path is not None:
                updates.append("pre_cancel_screenshot_path = ?")
                params.append(pre_cancel_screenshot_path)

            params.append(sub_id)
            query = f"UPDATE subscriptions SET {', '.join(updates)} WHERE id = ?;"
            cursor.execute(query, params)
            conn.commit()

        return self.get_subscription(sub_id)

    def get_total_savings(self) -> float:
        """Calculate the total money saved from all CANCELLED subscriptions."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COALESCE(SUM(amount), 0.0) as total FROM subscriptions WHERE status = ?;",
                (SubscriptionStatus.CANCELLED.value,),
            )
            row = cursor.fetchone()
            return float(row["total"]) if row else 0.0

    def delete_subscription(self, sub_id: int) -> bool:
        """Delete a subscription from the ledger."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM subscriptions WHERE id = ?;", (sub_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_model(self, row: sqlite3.Row) -> SubscriptionItem:
        """Convert a SQLite row to a SubscriptionItem Pydantic model."""
        renewal_dt = datetime.fromisoformat(row["renewal_date"])
        created_dt = datetime.fromisoformat(row["created_at"])
        updated_dt = datetime.fromisoformat(row["updated_at"])

        return SubscriptionItem(
            id=row["id"],
            service_name=row["service_name"],
            plan_name=row["plan_name"],
            amount=row["amount"],
            currency=row["currency"],
            billing_cycle=row["billing_cycle"],
            renewal_date=renewal_dt,
            cancellation_url=row["cancellation_url"],
            login_url=row["login_url"],
            status=SubscriptionStatus(row["status"]),
            proof_screenshot_path=row["proof_screenshot_path"],
            pre_cancel_screenshot_path=row["pre_cancel_screenshot_path"],
            created_at=created_dt,
            updated_at=updated_dt,
        )


_db_instance: Optional[Database] = None


def get_db(db_path: Optional[str] = None) -> Database:
    """Singleton getter for Database instance."""
    global _db_instance
    if _db_instance is None or (db_path and _db_instance.db_path != db_path):
        _db_instance = Database(db_path)
    return _db_instance
