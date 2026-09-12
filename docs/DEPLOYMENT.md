# Sub Guillotine Deployment Guide

## Overview

Sub Guillotine is designed to operate as an autonomous, background financial defense agent. It runs continuously without requiring user attendance, waking up periodically to monitor billing deadlines, navigating deceptive cancellation funnels headlessly via Playwright, and surfacing exclusively when an actionable human decision is required.

---

## Architecture: Autonomous Background Operation

```
+-------------------------------------------------------------------------+
|                           AWS / HOST ENVIRONMENT                        |
|                                                                         |
|   +-----------------------------------------------------------------+   |
|   |                  Sub Guillotine Background Daemon               |   |
|   |                     (--daemon --interval 3600)                  |   |
|   +-------------------------------+---------------------------------+   |
|                                   |                                     |
|             Periodic Scan Every   | Check SQLite Ledger                 |
|             1 Hour                | for Imminent Renewals (<24h)        |
|                                   v                                     |
|   +-------------------------------+---------------------------------+   |
|   |                        Decision Engine                          |   |
|   |         Are any subscriptions renewing in <= 24 hours?          |   |
|   +---------------+-------------------------------+-----------------+   |
|                   | No                            | Yes                 |
|                   v                               v                     |
|            Sleep Quietly                  Phase 3: Stage Cancel         |
|            (Zero Noise)                   (Playwright Headless)         |
|                                                   |                     |
|                                                   v                     |
|                                        Phase 4: Human-in-the-Loop       |
|                                        (Telegram Bot API Dispatch)      |
+---------------------------------------------------|---------------------+
                                                    | Push Notification
                                                    | with Screenshot
                                                    v
                                         +---------------------+
                                         |   User Smartphone   |
                                         |    (Telegram UI)    |
                                         +----------+----------+
                                                    |
                                                    | Tap [Confirm Cancel]
                                                    v
+---------------------------------------------------+---------------------+
|   Phase 5: Guillotine Strike                                            |
|   - Playwright clicks final confirmation                                |
|   - Proof screenshot captured and archived                              |
|   - SQLite ledger updated with saved dollars                            |
+-------------------------------------------------------------------------+
```

---

## Deployment Models

Sub Guillotine supports four deployment targets:

### 1. AgentCore Deployment (Recommended for Hackathon Scoring)

AgentCore provides the serverless deployment and execution runtime for Strands agents.

* **Manifest**: [`agentcore.json`](../agentcore.json) defines the agent metadata, tool schemas, container entrypoint, and financial safety guardrails.
* **Packaging**:
  ```bash
  # Validate AgentCore manifest
  python -c "import json; json.load(open('agentcore.json'))"
  ```
* **Deployment Flow**:
  1. Register the container image with your AWS container registry (Amazon ECR).
  2. Deploy via AgentCore CLI or AWS Bedrock Agent console using `agentcore.json`.
  3. The runtime schedules the background daemon, mapping environment variables for Bedrock and Telegram credentials.

---

### 2. Docker Container Deployment

Deploy Sub Guillotine on any container-compatible cloud host (AWS ECS, AWS App Runner, Fly.io, or VPS).

#### Build the Container Image
```bash
docker build -t sub-guillotine:latest .
```

#### Run with Docker Compose
1. Ensure your `.env` file is configured with AWS and Telegram credentials.
2. Launch the containerized daemon:
   ```bash
   docker compose up -d
   ```
3. Check daemon logs:
   ```bash
   docker compose logs -f sub-guillotine
   ```
4. Stop the container:
   ```bash
   docker compose down
   ```

---

### 3. AWS ECS (Elastic Container Service) / Fargate

For production serverless hosting:

1. **Push Container to Amazon ECR**:
   ```bash
   aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
   docker tag sub-guillotine:latest <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sub-guillotine:latest
   docker push <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com/sub-guillotine:latest
   ```
2. **Create ECS Fargate Task**:
   * CPU: 1 vCPU
   * Memory: 2 GB (provides sufficient memory for headless Chromium)
   * Environment Variables: `HEADLESS_BROWSER=true`, `HITL_MODE=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   * Persistent Volume: Mount Amazon EFS to `/data` for `sub_guillotine.db` and `/app/screenshots`.

---

### 4. Local Background Daemon

To run Sub Guillotine as a background process on your local development machine:

#### Windows PowerShell
```powershell
# Run with hourly background polling
.venv\Scripts\python.exe -m src.main --daemon --interval 3600
```

#### Linux / macOS
```bash
# Run with background nohup process
nohup python -m src.main --daemon --interval 3600 > daemon.log 2>&1 &
```

---

## Daemon Command-Line Flags

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--daemon` | `False` | Enables continuous background daemon worker mode. |
| `--interval <sec>` | `3600` | Polling frequency in seconds (e.g. `3600` for hourly). |
| `--max-iterations <N>` | `None` | Optional limit on daemon iterations (useful for testing). |
| `--live-time` | `False` | Uses current real-world UTC time instead of reference mock time. |
| `--auto-cancel` | `False` | Automatically executes cancellations without prompting. |
| `--status` | `False` | Prints the current SQLite ledger and cumulative savings. |
| `--start-portal` | `False` | Runs the standalone mock SaaS dark-pattern portal. |

---

## Security & Privacy Considerations

* **No Credential Storage**: Sub Guillotine does not store user banking passwords. It navigates sessions via session cookies or automated staging flows.
* **Hard Stop Gate**: The agent is architecturally barred from completing financial cancellations without explicit user confirmation (`c` on CLI or Telegram inline button).
* **Auditable Evidence**: Every action produces timestamped visual proof in `screenshots/` so the user can verify the exact state of their account before and after cancellation.
