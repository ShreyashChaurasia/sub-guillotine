"""SQLite storage and ledger management for Sub Guillotine."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Generator, List, Optional

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

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for sqlite3 connection ensuring automatic commit and close."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
        finally:
            conn.close()

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
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_subscriptions_service
                ON subscriptions(service_name);
                """
            )
            conn.commit()

        # Deduplicate any existing duplicate entries from prior runs
        self.deduplicate_ledger()

    def deduplicate_ledger(self) -> int:
        """Remove duplicate subscription records per service_name, preserving CANCELLED state and latest entries."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM subscriptions
                WHERE id NOT IN (
                    SELECT id FROM (
                        SELECT id, ROW_NUMBER() OVER (
                            PARTITION BY LOWER(TRIM(service_name))
                            ORDER BY CASE WHEN status = 'CANCELLED' THEN 0 ELSE 1 END, id DESC
                        ) as rn
                        FROM subscriptions
                    ) WHERE rn = 1
                );
                """
            )
            deleted_count = cursor.rowcount
            conn.commit()
            return deleted_count

    def get_subscription_by_service(
        self, service_name: str, plan_name: Optional[str] = None
    ) -> Optional[SubscriptionItem]:
        """Fetch an existing subscription by service name (case-insensitive)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if plan_name:
                cursor.execute(
                    """
                    SELECT * FROM subscriptions
                    WHERE LOWER(TRIM(service_name)) = LOWER(TRIM(?))
                      AND LOWER(TRIM(COALESCE(plan_name, ''))) = LOWER(TRIM(?))
                    ORDER BY CASE WHEN status = 'CANCELLED' THEN 0 ELSE 1 END, id DESC
                    LIMIT 1;
                    """,
                    (service_name, plan_name),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM subscriptions
                    WHERE LOWER(TRIM(service_name)) = LOWER(TRIM(?))
                    ORDER BY CASE WHEN status = 'CANCELLED' THEN 0 ELSE 1 END, id DESC
                    LIMIT 1;
                    """,
                    (service_name,),
                )
            row = cursor.fetchone()
            if not row:
                return None
            return self._row_to_model(row)

    def add_subscription(self, sub: SubscriptionItem) -> SubscriptionItem:
        """
        Insert or update (upsert) a subscription in the ledger to prevent duplicate records.
        If an entry for this service already exists:
        - If CANCELLED, preserve CANCELLED status.
        - If active (MONITORING/STAGED/KEPT), update renewal date, amount, and links.
        """
        existing = self.get_subscription_by_service(sub.service_name, sub.plan_name)
        now_str = datetime.now(timezone.utc).isoformat()
        renewal_iso = sub.renewal_date.isoformat()

        if existing and existing.id is not None:
            # If already cancelled, preserve CANCELLED status
            if existing.status == SubscriptionStatus.CANCELLED:
                return existing

            # Otherwise update existing subscription with latest details
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    UPDATE subscriptions SET
                        plan_name = COALESCE(?, plan_name),
                        amount = ?,
                        currency = ?,
                        billing_cycle = ?,
                        renewal_date = ?,
                        cancellation_url = COALESCE(?, cancellation_url),
                        login_url = COALESCE(?, login_url),
                        updated_at = ?
                    WHERE id = ?;
                    """,
                    (
                        sub.plan_name,
                        sub.amount,
                        sub.currency,
                        sub.billing_cycle,
                        renewal_iso,
                        sub.cancellation_url,
                        sub.login_url,
                        now_str,
                        existing.id,
                    ),
                )
                conn.commit()
            return self.get_subscription(existing.id)  # type: ignore

        # New subscription entry
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
