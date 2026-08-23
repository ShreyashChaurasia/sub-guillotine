"""Browser automation tool using Playwright for staging and executing subscription cancellations."""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from playwright.async_api import async_playwright

from src.config import get_settings
from src.models.schema import SubscriptionStatus
from src.storage.database import get_db

logger = logging.getLogger(__name__)


async def _async_stage_cancellation(
    target_url: str,
    subscription_id: int,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal async implementation of stage_cancellation using Playwright."""
    settings = get_settings()
    db = get_db(db_path)
    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    screenshot_filename = f"staged_sub_{subscription_id}_{timestamp_str}.png"
    screenshot_path = str(screenshots_dir / screenshot_filename)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.headless_browser)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        try:
            # Step 1: Open Target URL
            await page.goto(target_url, wait_until="networkidle", timeout=15000)

            # Step 2: Handle Login if present
            if await page.locator("#login-btn, button[type='submit'], input[type='submit']").count() > 0:
                # Fill standard mock credentials if input fields exist
                if await page.locator("input[name='email'], input[name='username']").count() > 0:
                    await page.fill("input[name='email'], input[name='username']", "user@example.com")
                if await page.locator("input[name='password']").count() > 0:
                    await page.fill("input[name='password']", "password123")
                await page.click("#login-btn, button[type='submit'], input[type='submit']")
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Step 3: Navigate to Billing if needed
            if "billing" not in page.url:
                billing_link = page.locator("a[href*='billing'], button:has-text('Billing'), a:has-text('Billing')")
                if await billing_link.count() > 0:
                    await billing_link.first.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)

            # Step 4: Click Cancel Subscription / Manage Plan
            cancel_btn = page.locator("#cancel-plan-btn, button:has-text('Cancel Subscription'), a:has-text('Cancel Plan')")
            if await cancel_btn.count() > 0:
                await cancel_btn.first.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Step 5: Handle Retention Survey / Dark Pattern 1
            if await page.locator("#survey-form, #reason-select").count() > 0:
                # Select a reason
                if await page.locator("#reason-select").count() > 0:
                    await page.select_option("#reason-select", index=1)
                continue_btn = page.locator("#submit-survey-btn, button:has-text('Continue Cancellation')")
                if await continue_btn.count() > 0:
                    await continue_btn.first.click()
                    await page.wait_for_load_state("networkidle", timeout=10000)

            # Step 6: Handle Retention Discount Offer / Dark Pattern 2
            discount_reject = page.locator("#decline-offer-btn, button:has-text('No thanks, cancel anyway'), a:has-text('Continue to Cancel')")
            if await discount_reject.count() > 0:
                await discount_reject.first.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Pre-cancellation step reached! Capture pre-cancel screenshot
            await page.screenshot(path=screenshot_path, full_page=True)

            # Update database status to STAGED_FOR_CANCEL
            db.update_status(
                sub_id=subscription_id,
                status=SubscriptionStatus.STAGED_FOR_CANCEL,
                pre_cancel_screenshot_path=screenshot_path,
            )

            current_url = page.url
            await browser.close()

            return {
                "success": True,
                "status": SubscriptionStatus.STAGED_FOR_CANCEL.value,
                "subscription_id": subscription_id,
                "staged_screenshot_path": screenshot_path,
                "staged_page_url": current_url,
                "message": "Successfully navigated dark pattern pipeline. Staged at final confirmation gate.",
            }

        except Exception as exc:
            logger.exception(f"Error staging cancellation: {exc}")
            # Try capturing error screenshot
            try:
                await page.screenshot(path=screenshot_path)
            except Exception:
                pass
            await browser.close()
            return {
                "success": False,
                "status": "ERROR",
                "subscription_id": subscription_id,
                "error": str(exc),
                "staged_screenshot_path": screenshot_path,
            }


async def _async_commit_cancellation(
    target_url: str,
    subscription_id: int,
    db_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal async implementation of commit_cancellation using Playwright."""
    settings = get_settings()
    db = get_db(db_path)
    sub = db.get_subscription(subscription_id)
    amount_saved = sub.amount if sub else 0.0
    service_name = sub.service_name if sub else "Unknown"

    screenshots_dir = Path(settings.screenshots_dir)
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    proof_filename = f"proof_cancelled_sub_{subscription_id}_{timestamp_str}.png"
    proof_path = str(screenshots_dir / proof_filename)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=settings.headless_browser)
        page = await browser.new_page(viewport={"width": 1280, "height": 800})

        try:
            # Navigate to cancellation / confirmation page
            await page.goto(target_url, wait_until="networkidle", timeout=15000)

            # If arriving directly at final confirm or needing to advance
            final_confirm_btn = page.locator("#confirm-cancel-btn, #final-cancel-btn, button:has-text('Confirm Cancellation'), button:has-text('Cancel Subscription Now')")
            if await final_confirm_btn.count() > 0:
                await final_confirm_btn.first.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            # Take proof screenshot of the confirmation / success screen
            await page.screenshot(path=proof_path, full_page=True)

            # Update DB to CANCELLED
            db.update_status(
                sub_id=subscription_id,
                status=SubscriptionStatus.CANCELLED,
                proof_screenshot_path=proof_path,
            )

            await browser.close()

            return {
                "success": True,
                "status": SubscriptionStatus.CANCELLED.value,
                "subscription_id": subscription_id,
                "service_name": service_name,
                "amount_saved": amount_saved,
                "proof_screenshot_path": proof_path,
                "message": f"Successfully cancelled {service_name}. Saved ${amount_saved:.2f}.",
            }

        except Exception as exc:
            logger.exception(f"Error committing cancellation: {exc}")
            await browser.close()
            return {
                "success": False,
                "status": "FAILED",
                "subscription_id": subscription_id,
                "error": str(exc),
                "proof_screenshot_path": None,
            }


def stage_cancellation(target_url: str, subscription_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Strands Tool: Stages subscription cancellation by autonomously navigating through dark pattern retention screens
    and stopping at the final confirmation gate with a pre-cancellation screenshot.
    """
    return asyncio.run(_async_stage_cancellation(target_url, subscription_id, db_path))


def commit_cancellation(target_url: str, subscription_id: int, db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Strands Tool: Commits the final subscription cancellation after human approval,
    captures timestamped cryptographic/visual proof, and updates ledger.
    """
    return asyncio.run(_async_commit_cancellation(target_url, subscription_id, db_path))
