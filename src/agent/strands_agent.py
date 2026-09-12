"""Sub Guillotine Strands Agent orchestrator."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.table import Table

from src.agent.system_prompt import AGENT_SYSTEM_PROMPT
from src.config import get_bedrock_client, get_settings
from src.models.schema import (
    ExtractedSubscriptionData,
    HITLDecisionType,
    SubscriptionItem,
    SubscriptionStatus,
)
from src.storage.database import Database, get_db
from src.tools.browser_canceler import commit_cancellation, stage_cancellation
from src.tools.deadline_tracker import check_imminent_deadlines
from src.tools.email_extractor import extract_subscription_from_email
from src.tools.hitl_notifier import dispatch_hitl_decision

logger = logging.getLogger(__name__)
console = Console()

TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "extract_subscription_from_email",
            "description": "Extracts structured subscription details from raw email text or HTML.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "email_content": {"type": "string", "description": "Raw body of the email"},
                        "email_subject": {"type": "string", "description": "Subject line of the email"},
                    },
                    "required": ["email_content"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "check_imminent_deadlines",
            "description": "Scans the SQLite ledger for subscriptions renewing within a threshold.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "threshold_hours": {"type": "integer", "description": "Hours threshold (default: 24)"},
                        "reference_time_iso": {"type": "string", "description": "ISO timestamp for reference time"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "stage_cancellation",
            "description": "Navigates headless browser through dark patterns up to the final cancel confirmation.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "target_url": {"type": "string", "description": "URL to the billing or cancel portal"},
                        "subscription_id": {"type": "integer", "description": "Database ID of subscription"},
                    },
                    "required": ["target_url", "subscription_id"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "dispatch_hitl_decision",
            "description": "Dispatches human-in-the-loop decision prompt to authorize or reject cancellation.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "subscription_id": {"type": "integer"},
                        "service_name": {"type": "string"},
                        "amount": {"type": "number"},
                        "currency": {"type": "string"},
                        "hours_remaining": {"type": "number"},
                        "staged_screenshot_path": {"type": "string"},
                    },
                    "required": ["subscription_id", "service_name", "amount"],
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "commit_cancellation",
            "description": "Executes final cancellation click on page and records proof screenshot.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "target_url": {"type": "string", "description": "URL where cancellation was staged"},
                        "subscription_id": {"type": "integer", "description": "Database ID of subscription"},
                    },
                    "required": ["target_url", "subscription_id"],
                }
            },
        }
    },
]


class StrandsAgent:
    """Orchestrator agent implementing the 5-phase Sub Guillotine workflow."""

    def __init__(self, db: Optional[Database] = None):
        self.settings = get_settings()
        self.db = db or get_db()
        self.tool_map = {
            "extract_subscription_from_email": extract_subscription_from_email,
            "check_imminent_deadlines": check_imminent_deadlines,
            "stage_cancellation": stage_cancellation,
            "dispatch_hitl_decision": dispatch_hitl_decision,
            "commit_cancellation": commit_cancellation,
        }

    def process_email(self, email_data: Dict[str, Any]) -> SubscriptionItem:
        """Phase 1: Ingest email, extract fields, and persist to SQLite ledger."""
        extracted_dict = extract_subscription_from_email(
            email_content=email_data.get("body_text") or email_data.get("body_html", ""),
            email_subject=email_data.get("subject", ""),
        )
        extracted = ExtractedSubscriptionData(**extracted_dict)

        sub_item = SubscriptionItem(
            service_name=extracted.service_name,
            plan_name=extracted.plan_name,
            amount=extracted.amount,
            currency=extracted.currency,
            billing_cycle=extracted.billing_cycle,
            renewal_date=extracted.renewal_date,
            cancellation_url=extracted.cancellation_url,
            login_url=extracted.login_url,
            status=SubscriptionStatus.MONITORING,
        )
        saved = self.db.add_subscription(sub_item)
        return saved

    def run_guillotine_pipeline(
        self,
        emails: List[Dict[str, Any]],
        reference_time: Optional[datetime] = None,
        auto_decision: Optional[str] = None,
        interactive: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes the complete end-to-end 5-phase financial defense pipeline.
        """
        ref_time = reference_time or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        results = {
            "ingested_count": 0,
            "imminent_count": 0,
            "staged_count": 0,
            "cancelled_count": 0,
            "kept_count": 0,
            "total_saved": 0.0,
            "actions": [],
        }

        # PHASE 1: SCAN & INGEST
        console.print("\n[bold cyan]=== PHASE 1: SCAN (Email Ingestion & Extraction) ===[/bold cyan]")
        for email in emails:
            sub = self.process_email(email)
            results["ingested_count"] += 1
            if sub.status == SubscriptionStatus.CANCELLED:
                console.print(f"  [dim yellow][ALREADY CANCELLED][/dim yellow] [bold]{sub.service_name}[/bold] (${sub.amount:.2f} {sub.currency}) - Preserving cancelled status")
            else:
                console.print(f"  [green][OK][/green] Ingested [bold]{sub.service_name}[/bold] (${sub.amount:.2f} {sub.currency}) renewing on {sub.renewal_date.strftime('%Y-%m-%d %H:%M UTC')}")

        # PHASE 2: DETECT IMMINENT DEADLINES
        console.print(f"\n[bold cyan]=== PHASE 2: DETECT (Threshold: {self.settings.deadline_threshold_hours}h) ===[/bold cyan]")
        imminent = self.db.get_imminent_subscriptions(
            threshold_hours=self.settings.deadline_threshold_hours,
            reference_time=ref_time,
        )
        results["imminent_count"] = len(imminent)
        console.print(f"  Found [bold yellow]{len(imminent)}[/bold yellow] subscription(s) facing imminent renewal.")

        # PROCESS EACH IMMINENT SUBSCRIPTION
        for item in imminent:
            sub = item.subscription
            sub_id = sub.id
            if sub_id is None:
                continue

            console.print(f"\n[bold magenta]Targeting Subscription #{sub_id}: {sub.service_name} (${sub.amount:.2f})[/bold magenta]")
            console.print(f"  Deadline: {item.hours_remaining:.1f} hours remaining ({'CRITICAL' if item.is_critical else 'UPCOMING'})")

            # PHASE 3: STAGE CANCELLATION (Headless Browser)
            console.print("[bold cyan]=== PHASE 3: STAGE (Navigating Dark Pattern Maze) ===[/bold cyan]")
            target_url = sub.cancellation_url or f"{self.settings.mock_portal_url}/billing"
            
            stage_result = stage_cancellation(target_url=target_url, subscription_id=sub_id, db_path=self.db.db_path)
            staged_screenshot = stage_result.get("staged_screenshot_path")
            results["staged_count"] += 1
            console.print(f"  [green][STAGED][/green] Reached final confirmation gate.")
            if staged_screenshot:
                console.print(f"  [dim]Pre-cancel proof: {staged_screenshot}[/dim]")

            # PHASE 4: HUMAN-IN-THE-LOOP APPROVAL GATE
            console.print("[bold cyan]=== PHASE 4: ASK (Human-in-the-Loop Gate) ===[/bold cyan]")
            decision_dict = dispatch_hitl_decision(
                subscription_id=sub_id,
                service_name=sub.service_name,
                amount=sub.amount,
                currency=sub.currency,
                hours_remaining=item.hours_remaining,
                staged_screenshot_path=staged_screenshot,
                interactive=interactive,
                auto_decision=auto_decision,
                db_path=self.db.db_path,
            )

            decision_type = decision_dict.get("decision")

            # PHASE 5: EXECUTE OR STAND DOWN
            if decision_type == HITLDecisionType.CANCEL.value:
                console.print("[bold cyan]=== PHASE 5a: EXECUTE (Guillotine Strike) ===[/bold cyan]")
                commit_result = commit_cancellation(
                    target_url=stage_result.get("staged_page_url") or target_url,
                    subscription_id=sub_id,
                    db_path=self.db.db_path,
                )
                results["cancelled_count"] += 1
                results["total_saved"] += sub.amount
                results["actions"].append({
                    "subscription_id": sub_id,
                    "service_name": sub.service_name,
                    "action": "CANCELLED",
                    "amount_saved": sub.amount,
                    "proof": commit_result.get("proof_screenshot_path"),
                })
                console.print(f"  [bold green][CANCELLED] Saved ${sub.amount:.2f} {sub.currency}[/bold green]")
                if commit_result.get("proof_screenshot_path"):
                    console.print(f"  [dim]Proof screenshot saved: {commit_result.get('proof_screenshot_path')}[/dim]")
            else:
                console.print("[bold cyan]=== PHASE 5b: STAND DOWN (Retaining Subscription) ===[/bold cyan]")
                results["kept_count"] += 1
                results["actions"].append({
                    "subscription_id": sub_id,
                    "service_name": sub.service_name,
                    "action": "KEPT",
                    "amount_saved": 0.0,
                })
                console.print(f"  [yellow][KEPT] Subscription preserved per operator request.[/yellow]")

        # PRINT FINAL SUMMARY REPORT
        self.render_summary(results)
        return results

    def render_summary(self, results: Dict[str, Any]) -> None:
        """Render a polished Rich table summarizing pipeline execution."""
        console.print("\n")
        table = Table(title="[bold green]SUB GUILLOTINE EXECUTION REPORT[/bold green]", expand=False)
        table.add_column("Metric", style="bold cyan")
        table.add_column("Value", style="bold white")

        table.add_row("Total Subscriptions Scanned", str(results["ingested_count"]))
        table.add_row("Imminent Renewals (<24h)", str(results["imminent_count"]))
        table.add_row("Cancellations Staged", str(results["staged_count"]))
        table.add_row("Cancellations Executed", f"[green]{results['cancelled_count']}[/green]")
        table.add_row("Subscriptions Preserved (Kept)", f"[yellow]{results['kept_count']}[/yellow]")
        table.add_row("Total Money Saved", f"[bold green]${results['total_saved']:.2f} USD[/bold green]")

        console.print(table)
        console.print()
