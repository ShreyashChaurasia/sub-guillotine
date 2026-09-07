"""Sub Guillotine CLI Entry Point and Interactive Runner."""

import argparse
import json
import logging
import multiprocessing
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from rich.console import Console
from rich.table import Table

from src.agent.strands_agent import StrandsAgent
from src.config import get_settings
from src.mock_services.mock_saas_portal import run_server
from src.storage.database import get_db

console = Console()
logging.basicConfig(level=logging.WARNING)


def print_banner():
    """Print Sub Guillotine ASCII header banner."""
    banner = r"""[bold red]
  ____  _   _ ____     ____ _   _ ___ _     _     ___ _____ ___ _   _ _____ 
 / ___|| | | | __ )   / ___| | | |_ _| |   | |   / _ \_   _|_ _| \ | | ____|
 \___ \| | | |  _ \  | |  _| |_| || || |   | |  | | | || |  | ||  \| |  _|  
  ___) | |_| | |_) | | |_| | |_| || || |___| |__| |_| || |  | || |\  | |___ 
 |____/ \___/|____/   \____|\___/|___|_____|_____\___/ |_| |___|_| \_|_____|
[/bold red]
[bold white]AUTONOMOUS FINANCIAL DEFENSE AGENT -- HUNTING RECURRING SUBSCRIPTIONS[/bold white]
[dim]Powered by Amazon Bedrock & Playwright Automation[/dim]
"""
    console.print(banner)


def show_ledger_status(db_path: str = None):
    """Display current database ledger and total money saved."""
    db = get_db(db_path)
    subs = db.get_all_subscriptions()
    total_saved = db.get_total_savings()

    table = Table(title="[bold green]CURRENT SUBSCRIPTION LEDGER[/bold green]", expand=True)
    table.add_column("ID", justify="center", style="bold cyan", width=4)
    table.add_column("Service Name", style="bold white")
    table.add_column("Amount", justify="right", style="bold yellow")
    table.add_column("Renewal Date (UTC)", style="white")
    table.add_column("Status", justify="center")

    for s in subs:
        status_color = "green" if s.status.value == "CANCELLED" else ("yellow" if s.status.value == "MONITORING" else "cyan")
        table.add_row(
            str(s.id),
            s.service_name,
            f"${s.amount:.2f} {s.currency}",
            s.renewal_date.strftime("%Y-%m-%d %H:%M"),
            f"[{status_color}]{s.status.value}[/{status_color}]",
        )

    console.print(table)
    console.print(f"\n[bold green]Total Money Saved to Date: ${total_saved:.2f} USD[/bold green]\n")


def main():
    parser = argparse.ArgumentParser(description="Sub Guillotine -- Autonomous Subscription Defense Agent")
    parser.add_argument("--demo", action="store_true", help="Run automated end-to-end demo flow")
    parser.add_argument("--auto-cancel", action="store_true", help="Auto-approve cancellations without interactive prompt")
    parser.add_argument("--status", action="store_true", help="Show current subscriptions ledger and savings")
    parser.add_argument("--start-portal", action="store_true", help="Start the mock SaaS portal standalone")
    parser.add_argument("--emails", type=str, default="src/mock_services/sample_emails.json", help="Path to sample emails JSON")

    args = parser.parse_args()
    print_banner()

    settings = get_settings()

    if args.start_portal:
        console.print(f"[bold green]Starting Mock SaaS Portal on http://{settings.mock_portal_host}:{settings.mock_portal_port}...[/bold green]")
        run_server(host=settings.mock_portal_host, port=settings.mock_portal_port)
        return

    if args.status:
        show_ledger_status()
        return

    # Start mock portal server in background process for E2E flow
    server_process = multiprocessing.Process(
        target=run_server,
        kwargs={"host": settings.mock_portal_host, "port": settings.mock_portal_port},
        daemon=True,
    )
    server_process.start()
    time.sleep(1.0)  # Brief wait for FastAPI to bind

    try:
        # Load sample emails
        emails_path = Path(args.emails)
        if not emails_path.exists():
            console.print(f"[bold red]Error: Emails file not found at {emails_path}[/bold red]")
            sys.exit(1)

        with open(emails_path, "r", encoding="utf-8") as f:
            sample_emails = json.load(f)

        agent = StrandsAgent()
        
        # Simulated current time (August 23, 2026 at 12:00 UTC)
        simulated_time = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

        auto_decision = "CANCEL" if args.auto_cancel else (None if not args.demo else "CANCEL")
        interactive = not args.auto_cancel and not args.demo

        agent.run_guillotine_pipeline(
            emails=sample_emails,
            reference_time=simulated_time,
            auto_decision=auto_decision,
            interactive=interactive,
        )

        show_ledger_status()

    finally:
        if server_process.is_alive():
            server_process.terminate()
            server_process.join(timeout=1.0)


if __name__ == "__main__":
    main()
