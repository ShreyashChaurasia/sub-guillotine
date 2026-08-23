"""Mock SaaS Portal with Dark Pattern Cancellation Flow built with FastAPI."""

from datetime import datetime, timezone
from fastapi import FastAPI, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn

app = FastAPI(title="SaaSPro Mock Customer Portal")

# Basic styling template
PAGE_LAYOUT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — SaaSPro Analytics</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f172a;
            color: #f8fafc;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }}
        .container {{
            background: #1e293b;
            border-radius: 12px;
            padding: 32px;
            width: 100%;
            max-width: 520px;
            box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5), 0 8px 10px -6px rgba(0, 0, 0, 0.5);
            border: 1px solid #334155;
        }}
        h1, h2, h3 {{ color: #ffffff; margin-top: 0; }}
        .badge {{ background: #3b82f6; color: white; padding: 4px 8px; border-radius: 6px; font-size: 12px; }}
        .btn {{
            display: inline-block;
            width: 100%;
            padding: 12px;
            margin: 8px 0;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            text-align: center;
            box-sizing: border-box;
            text-decoration: none;
            border: none;
            font-size: 15px;
        }}
        .btn-primary {{ background: #2563eb; color: white; }}
        .btn-primary:hover {{ background: #1d4ed8; }}
        .btn-danger {{ background: #dc2626; color: white; }}
        .btn-danger:hover {{ background: #b91c1c; }}
        .btn-secondary {{ background: #475569; color: #f8fafc; }}
        .btn-secondary:hover {{ background: #334155; }}
        .btn-offer {{ background: #10b981; color: white; font-size: 16px; padding: 14px; }}
        .input-group {{ margin-bottom: 16px; text-align: left; }}
        label {{ display: block; margin-bottom: 6px; font-size: 14px; color: #94a3b8; }}
        input, select {{
            width: 100%;
            padding: 10px;
            border-radius: 6px;
            border: 1px solid #475569;
            background: #0f172a;
            color: #fff;
            box-sizing: border-box;
        }}
        .offer-box {{
            background: linear-gradient(135deg, #1e3a8a, #065f46);
            padding: 20px;
            border-radius: 8px;
            border: 2px dashed #34d399;
            margin: 16px 0;
            text-align: center;
        }}
        .proof-box {{
            background: #064e3b;
            border: 1px solid #10b981;
            padding: 20px;
            border-radius: 8px;
            margin-top: 16px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        {content}
    </div>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
@app.get("/login", response_class=HTMLResponse)
async def login_page():
    content = """
    <h2>🔐 SaaSPro Portal Login</h2>
    <p style="color: #94a3b8; font-size: 14px;">Sign in to manage your team analytics subscription.</p>
    <form action="/login" method="POST">
        <div class="input-group">
            <label>Email Address</label>
            <input type="email" name="email" value="alex.chen@example.com" required />
        </div>
        <div class="input-group">
            <label>Password</label>
            <input type="password" name="password" value="••••••••••••" required />
        </div>
        <button id="login-btn" type="submit" class="btn btn-primary">Sign In to Account</button>
    </form>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Login", content=content))


@app.post("/login")
async def process_login(response: Response, email: str = Form("alex.chen@example.com")):
    res = RedirectResponse(url="/dashboard", status_code=303)
    res.set_cookie(key="session_user", value=email)
    return res


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page():
    content = """
    <h2>📊 Account Dashboard</h2>
    <p>Welcome back, <strong>Alex Chen</strong> <span class="badge">Active</span></p>
    <div style="background: #0f172a; padding: 16px; border-radius: 8px; margin: 16px 0; border: 1px solid #334155;">
        <p style="margin: 4px 0;"><strong>Current Plan:</strong> Pro Tier ($29.00 / month)</p>
        <p style="margin: 4px 0; color: #f59e0b;"><strong>Next Billing Date:</strong> August 24, 2026</p>
    </div>
    <a id="billing-link" href="/billing" class="btn btn-primary">💳 Manage Billing & Subscription</a>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Dashboard", content=content))


@app.get("/billing", response_class=HTMLResponse)
async def billing_page():
    content = """
    <h2>💳 Billing & Subscription</h2>
    <div style="background: #0f172a; padding: 16px; border-radius: 8px; margin: 16px 0; border: 1px solid #334155;">
        <p style="margin: 4px 0;"><strong>Active Subscription:</strong> SaaSPro Pro Tier</p>
        <p style="margin: 4px 0;"><strong>Renewal Cost:</strong> $29.00 USD / month</p>
        <p style="margin: 4px 0;"><strong>Payment Method:</strong> Visa ending in 4242</p>
        <p style="margin: 4px 0; color: #ef4444;"><strong>Auto-renewal:</strong> Enabled (Aug 24, 2026)</p>
    </div>
    <a id="cancel-plan-btn" href="/cancel-survey" class="btn btn-danger">Cancel Plan</a>
    <a href="/dashboard" class="btn btn-secondary">Return to Dashboard</a>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Billing", content=content))


@app.get("/cancel-survey", response_class=HTMLResponse)
async def cancel_survey_page():
    content = """
    <h2>📝 Cancellation Survey (Dark Pattern #1)</h2>
    <p style="color: #94a3b8; font-size: 14px;">We're sorry to see you go. Please tell us why you are leaving before we proceed.</p>
    <form action="/retention-offer" method="GET" id="survey-form">
        <div class="input-group">
            <label>Primary reason for leaving</label>
            <select name="reason" id="reason-select">
                <option value="too_expensive">Too expensive / not using enough</option>
                <option value="missing_features">Missing required analytics features</option>
                <option value="switching">Switching to a different tool</option>
                <option value="other">Temporary project finished</option>
            </select>
        </div>
        <button id="submit-survey-btn" type="submit" class="btn btn-primary">Continue Cancellation</button>
        <a href="/billing" class="btn btn-secondary">Nevermind, Keep Plan</a>
    </form>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Cancellation Survey", content=content))


@app.get("/retention-offer", response_class=HTMLResponse)
async def retention_offer_page():
    content = """
    <h2>🎁 Wait! Special Offer for You (Dark Pattern #2)</h2>
    <div class="offer-box">
        <h3 style="color: #34d399; margin-bottom: 8px;">Get 50% Off For the Next 6 Months!</h3>
        <p style="margin: 4px 0; font-size: 15px;">Stay on Pro Tier for just <strong>$14.50/month</strong> instead of $29.00.</p>
    </div>
    <a href="/dashboard" class="btn btn-offer">Claim 50% Discount & Stay</a>
    <a id="decline-offer-btn" href="/final-cancel" class="btn btn-danger" style="margin-top: 12px;">No thanks, continue to cancel anyway</a>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Retention Offer", content=content))


@app.get("/final-cancel", response_class=HTMLResponse)
async def final_cancel_page():
    content = """
    <h2>⚠️ Final Confirmation Gate</h2>
    <div style="background: #450a0a; border: 1px solid #ef4444; padding: 16px; border-radius: 8px; margin: 16px 0;">
        <p style="color: #fca5a5; margin: 0; font-weight: 600;">Warning: You will lose access to all analytics data, dashboards, and export features at the end of the billing cycle.</p>
    </div>
    <form action="/final-cancel" method="POST">
        <button id="confirm-cancel-btn" type="submit" class="btn btn-danger" style="font-size: 16px; padding: 14px;">Confirm & Finalize Cancellation</button>
    </form>
    <a href="/dashboard" class="btn btn-secondary">Keep My Subscription</a>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Final Cancellation Gate", content=content))


@app.post("/final-cancel", response_class=HTMLResponse)
async def process_final_cancel():
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    content = f"""
    <h2>✅ Subscription Successfully Cancelled</h2>
    <div class="proof-box">
        <h3 style="color: #34d399; margin: 0 0 8px 0;">Cancellation Confirmed</h3>
        <p style="margin: 4px 0;">Your SaaSPro Pro Tier subscription has been terminated.</p>
        <p style="margin: 4px 0; font-size: 13px; color: #a7f3d0;"><strong>Timestamp:</strong> {timestamp}</p>
        <p style="margin: 4px 0; font-size: 13px; color: #a7f3d0;"><strong>Confirmation ID:</strong> SG-CANCEL-88912-X</p>
        <p style="margin: 8px 0 0 0; font-weight: bold; color: #ffffff;">No further charges will be made to your payment method.</p>
    </div>
    <a href="/login" class="btn btn-secondary" style="margin-top: 16px;">Back to Home</a>
    """
    return HTMLResponse(PAGE_LAYOUT.format(title="Cancelled", content=content))


def run_server(host: str = "127.0.0.1", port: int = 8888):
    """Entry point to launch the mock portal server."""
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    run_server()
