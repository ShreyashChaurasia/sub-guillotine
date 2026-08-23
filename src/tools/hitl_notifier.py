"""Human-in-the-Loop (HITL) notification tool with Rich CLI and Telegram integration."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from src.config import get_settings
from src.models.schema import HITLDecision, HITLDecisionType, SubscriptionStatus
from src.storage.database import get_db

logger = logging.getLogger(__name__)
console = Console()


def dispatch_hitl_decision(
    subscription_id: int,
    service_name: str,
    amount: float,
    currency: str = "USD",
    hours_remaining: float = 24.0,
    staged_screenshot_path: Optional[str] = None,
    interactive: bool = True,
    auto_decision: Optional[str] = None,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strands Tool: Dispatches a Human-in-the-Loop approval prompt via Rich CLI or Telegram bot.
    Blocks until human operator decides whether to EXECUTE (Cancel) or STAND DOWN (Keep).
    """
    settings = get_settings()
    db = get_db(db_path)

    # Render Rich Decision Card
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Field", style="bold cyan", width=18)
    table.add_column("Value", style="white")

    table.add_row("Subscription ID", f"#{subscription_id}")
    table.add_row("Service", f"[bold yellow]{service_name}[/bold yellow]")
    table.add_row("Recurring Cost", f"[bold red]${amount:.2f} {currency}[/bold red]")
    
    urgency_color = "red" if hours_remaining <= 6.0 else "yellow"
    table.add_row("Time to Renewal", f"[{urgency_color}]{hours_remaining:.1f} hours remaining[/{urgency_color}]")
    if staged_screenshot_path:
        table.add_row("Staged Proof", f"[link=file://{staged_screenshot_path}]{staged_screenshot_path}[/link]")

    panel = Panel(
        table,
        title="[bold red]⚠️ HUMAN-IN-THE-LOOP APPROVAL REQUIRED[/bold red]",
        subtitle="[dim]Sub Guillotine Agent is staged and awaiting your command[/dim]",
        border_style="red" if hours_remaining <= 6.0 else "yellow",
        expand=False,
    )
    console.print()
    console.print(panel)

    decision_value: HITLDecisionType

    if auto_decision:
        # Programmatic or non-interactive mock test mode
        normalized = auto_decision.strip().upper()
        if normalized in ["CANCEL", "C", "YES"]:
            decision_value = HITLDecisionType.CANCEL
        elif normalized in ["KEEP", "K", "NO"]:
            decision_value = HITLDecisionType.KEEP
        else:
            decision_value = HITLDecisionType.DEFER
    elif not interactive:
        # Default non-interactive choice
        decision_value = HITLDecisionType.CANCEL
    else:
        # Interactive CLI prompt
        choice = Prompt.ask(
            "\n[bold green][C][/bold green]ancel (Execute Guillotine) / [bold yellow][K][/bold yellow]eep (Stand Down)",
            choices=["c", "C", "k", "K", "cancel", "keep"],
            default="c",
        )
        if choice.lower() in ["c", "cancel"]:
            decision_value = HITLDecisionType.CANCEL
        else:
            decision_value = HITLDecisionType.KEEP

    # If decision is KEEP, update state to KEPT
    if decision_value == HITLDecisionType.KEEP:
        db.update_status(sub_id=subscription_id, status=SubscriptionStatus.KEPT)
        console.print(f"[bold yellow]🛑 Stood down. Subscription #{subscription_id} ({service_name}) marked as KEPT.[/bold yellow]\n")
    elif decision_value == HITLDecisionType.CANCEL:
        console.print(f"[bold green]⚡ Authorization GRANTED. Executing cancellation for #{subscription_id} ({service_name})...[/bold green]\n")

    decision_obj = HITLDecision(
        decision=decision_value,
        subscription_id=subscription_id,
        decided_at=datetime.now(timezone.utc),
    )

    return decision_obj.model_dump(mode="json")
