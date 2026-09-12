# Sub Guillotine — Sprint Development Plan

> **Methodology:** Dynamic Agile (adaptive sprints with daily retro checkpoints)  
> **Hackathon Deadline:** September 14, 2026  
> **Start Date:** August 22, 2026  
> **Total Duration:** ~23 days (4 sprints)

---

## Sprint Overview

| Sprint | Focus | Deliverable |
|--------|-------|-------------|
| **Sprint 0** | Bootstrap & Scaffolding | Repo, deps, config, schemas, DB |
| **Sprint 1** | Core Tools & Agent | All 5 @tool functions + Strands agent |
| **Sprint 2** | Mock Environment & Integration | Mock portal, E2E flow, Playwright |
| **Sprint 3** | Polish, Tests & Documentation | README, architecture diagram, tests |
| **Sprint 4** | Demo, Video & Submission | Demo video, Devpost submission |

---

## Sprint 0: Bootstrap & Scaffolding (Aug 22-23)
**Goal:** Project foundation — zero functionality, all infrastructure.

### Tasks
- [x] Initialize git repo and push to GitHub
- [x] Add MIT License
- [x] Add .gitignore
- [x] Create directory structure (all `__init__.py` files)
- [x] Create `requirements.txt`
- [x] Create `.env.example`
- [x] Create `config.py` with Bedrock client initialization
- [x] Implement `src/models/schema.py` (Pydantic v2 models)
- [x] Implement `src/storage/database.py` (SQLite CRUD)
- [x] Write `tests/test_schema.py` and `tests/test_database.py`
- [x] Verify: `pip install -r requirements.txt` succeeds
- [x] Verify: `pytest tests/test_schema.py tests/test_database.py -v` passes

### Definition of Done
- [x] All dependencies install cleanly
- [x] Pydantic models serialize/deserialize correctly
- [x] SQLite operations (insert, query, update) pass unit tests
- [x] Config loads `.env` and initializes BedrockModel without errors

### Sprint 0 Retro Checkpoint
```
Date: 2026-08-23
Completed: Sprint 0 complete. All scaffolding, schemas, SQLite persistence, settings/config, and unit tests passing.
Blocked: None
Carry-over to Sprint 1: None
Notes: Ready for Sprint 1 (Tools & Strands Agent implementation).
```

---

## Sprint 1: Core Tools & Agent Assembly (Aug 24-29)
**Goal:** All five Strands `@tool` functions working + Agent harness assembled.

### Tasks

#### Day 1-2 (Aug 24-25): Email Extractor & Deadline Tracker
- [x] Create `src/mock_services/sample_emails.json` (4-5 mock emails)
- [x] Implement `@tool extract_subscription_from_email` in `src/tools/email_extractor.py`
  - Uses Bedrock to parse raw email → structured SubscriptionItem fields
  - Handles both HTML and plaintext email formats
  - Returns JSON dict with extracted fields
- [x] Implement `@tool check_imminent_deadlines` in `src/tools/deadline_tracker.py`
  - Queries SQLite for subscriptions with renewal_date within 24h
  - Returns list of imminent items with countdown timers
- [x] Unit test both tools with mock data

#### Day 3-4 (Aug 26-27): Browser Canceler (Playwright)
- [x] Install Playwright and Chromium: `playwright install chromium`
- [x] Implement `@tool stage_cancellation` in `src/tools/browser_canceler.py`
  - Launches headless Chromium
  - Navigates login → dashboard → billing → retention → final cancel
  - Stops at final confirmation button
  - Captures pre-cancellation screenshot
- [x] Implement `@tool commit_cancellation` in `src/tools/browser_canceler.py`
  - Clicks the final confirmation button
  - Waits for success state
  - Captures timestamped proof screenshot
  - Updates database status to CANCELLED
- [x] Test with a simple local HTML page first (before mock portal)

#### Day 5 (Aug 28): HITL Notifier
- [x] Implement `@tool dispatch_hitl_decision` in `src/tools/hitl_notifier.py`
  - CLI mode: Rich panel with CANCEL/KEEP prompt (blocking input)
  - Telegram mode: Send message with inline keyboard buttons (stretch)
- [x] Test CLI prompt flow manually

#### Day 6 (Aug 29): Agent Assembly & Smoke Test
- [x] Write `src/agent/system_prompt.py` with full agent persona
- [x] Implement `src/agent/strands_agent.py` — bind all 5 tools to Strands Agent
- [x] Smoke test: Agent can call each tool individually via natural language
- [x] Verify Bedrock API calls succeed with AWS credits

### Definition of Done
- [x] Each tool function works independently with test data
- [x] Agent responds to natural language commands and invokes correct tools
- [x] Playwright can navigate a simple multi-page HTML flow
- [x] Bedrock API calls complete without errors

### Sprint 1 Retro Checkpoint
```
Date: 2026-08-23
Completed: Sprint 1 complete. All 5 tools implemented, tested, and assembled into StrandsAgent.
Blocked: None
Carry-over to Sprint 2: None
Notes: Ready for mock portal & E2E integration.
```

---

## Sprint 2: Mock Environment & End-to-End Integration (Aug 30 - Sep 5)
**Goal:** Complete mock SaaS portal + full autonomous pipeline working end-to-end.

### Tasks

#### Day 1-2 (Aug 30-31): Mock SaaS Portal
- [x] Build `src/mock_services/mock_saas_portal.py` (FastAPI)
  - `GET /` → Login page (HTML form)
  - `POST /login` → Set session cookie, redirect to dashboard
  - `GET /dashboard` → Account overview with "Manage Billing" link
  - `GET /billing` → Billing info + "Cancel Plan" button
  - `GET /cancel-survey` → "Why leaving?" form
  - `POST /cancel-survey` → "Stay for 50% off!" retention popup
  - `GET /final-cancel` → Final "Confirm Cancellation" button
  - `POST /final-cancel` → Success page: "Subscription cancelled"
- [x] Each page has proper HTML with identifiable CSS selectors
- [x] Test portal manually in browser at `http://localhost:8888`

#### Day 3-4 (Sep 1-2): Playwright <-> Portal Integration
- [x] Update `stage_cancellation` to work with mock portal selectors
- [x] Update `commit_cancellation` to work with mock portal
- [x] Handle session cookies, form submissions, button clicks
- [x] Verify screenshot capture at each stage
- [x] Handle edge cases: timeouts, element not found, page errors

#### Day 5-6 (Sep 3-4): End-to-End Pipeline
- [x] Implement `src/main.py` with Rich CLI orchestration
  - Phase 1: Load mock emails → extract subscriptions → store in DB
  - Phase 2: Simulate time advancement → check deadlines
  - Phase 3: Agent stages cancellation via Playwright
  - Phase 4: HITL prompt → user decision
  - Phase 5: Execute/keep → proof screenshot → savings summary
- [x] Test full pipeline: `python -m src.main`
- [x] Fix any agent tool-chaining issues (prompt engineering)

#### Day 7 (Sep 5): Integration Testing
- [x] Write `tests/test_cancellation_flow.py` — full E2E test
  - Starts mock portal in background
  - Feeds mock email to agent
  - Verifies DB state transitions
  - Verifies screenshot files exist
  - Verifies final status
- [x] Run full test suite: `pytest tests/ -v`
- [x] Fix any flaky tests or timing issues

### Definition of Done
- [x] Mock portal serves all dark-pattern cancellation steps
- [x] Playwright navigates the full flow without errors
- [x] Agent orchestrates the complete pipeline autonomously
- [x] E2E test passes reliably
- [x] Demo-ready: can show the full loop in a terminal

### Sprint 2 Retro Checkpoint
```
Date: 2026-08-23
Completed: Sprint 2 complete. Mock portal, E2E integration test, and main CLI runner verified.
Blocked: None
Carry-over to Sprint 3: None
Notes: Ready for Sprint 3 (polish, documentation, README).
```

---

## Sprint 3: Polish, Tests & Documentation (Sep 6-10)
**Goal:** Production-quality code, comprehensive tests, README, architecture diagram.

### Tasks

#### Day 1-2 (Sep 6-7): Code Quality & Edge Cases
- [x] Add error handling to all tools (graceful failures)
- [x] Add logging throughout (Python `logging` module)
- [x] Handle network timeouts in Playwright
- [x] Handle Bedrock API rate limits / throttling
- [x] Add retry logic for transient failures
- [x] Support multiple concurrent subscriptions in single demo run

#### Day 3 (Sep 8): Test Coverage
- [x] Expand `tests/test_tools.py` -- edge cases for each tool
- [x] Add `tests/test_agent.py` -- agent decision-making tests
- [x] Target >80% test coverage on core modules (Achieved 83% overall, >90% core)
- [x] All tests pass: `pytest tests/ -v --tb=short` (33 passed)

#### Day 4-5 (Sep 9-10): Documentation & Submission Assets
- [x] Rewrite `README.md` with:
  - Project description & problem statement
  - Architecture diagram
  - Tech stack details
  - Setup & installation instructions
  - Environment configuration guide
  - Demo execution steps
  - Screenshots & proof paths
  - "Money saved" value proposition
- [x] Create architecture diagram (Mermaid)
- [x] Add inline code comments and docstrings
- [x] Telegram HITL integration (stretch goal)
  - [x] Telegram photo and alert dispatch via Bot API
  - [x] HITL notifications direct to chat

### Definition of Done
- [x] All tests pass with >80% coverage
- [x] README is comprehensive and submission-ready
- [x] Architecture diagram is polished and embedded
- [x] Code is clean, commented, and well-documented
- [x] Telegram integration working (stretch)

### Sprint 3 Retro Checkpoint
```
Date: 2026-09-07
Completed: Sprint 3 complete. Full retry handling, Playwright timeout resilience, Bedrock backoff, Telegram HITL alert dispatch, 33 unit/integration tests with 83% coverage.
Blocked: None
Carry-over to Sprint 4: None
Notes: Ready for Sprint 4 (demo recording, video walkthrough, and submission assets).
```

---

## Sprint 4: Demo, Video & Submission (Sep 11-14)
**Goal:** Record demo video, finalize submission, push to Devpost.

### Tasks

#### Day 1-2 (Sep 11-12): Demo Polish & Recording
- [ ] Practice the demo flow 3-5 times end-to-end
- [ ] Record demo video (≤5 minutes) covering:
  - Problem statement (30s)
  - Architecture overview (45s)
  - Live demo: email scan → tracking → staging → HITL → cancellation (2.5min)
  - Money saved summary (30s)
  - Future roadmap (30s)
- [ ] Edit video (add captions, trim dead air)
- [ ] Upload to YouTube/Loom (public/unlisted)

#### Day 3 (Sep 13): Devpost Submission
- [ ] Write Devpost description:
  - Inspiration
  - What it does
  - How we built it
  - Challenges we ran into
  - Accomplishments
  - What we learned
  - What's next
- [ ] Link GitHub repo, demo video, architecture diagram
- [ ] Final code push — clean up debug prints, temp files
- [ ] Tag release: `git tag v1.0.0-hackathon && git push --tags`

#### Day 4 (Sep 14): Final Checks & Submit
- [ ] Verify GitHub repo is public
- [ ] Verify README renders correctly on GitHub
- [ ] Verify demo video is accessible
- [ ] Submit on Devpost before 11:45 PM EDT
- [ ] Optional: Publish Build Story on builder.aws with #AgentsforHumans

### Definition of Done
- Demo video uploaded and publicly accessible
- Devpost submission complete with all required fields
- GitHub repo is clean, public, and tagged
- All tests still pass on clean clone

### Sprint 4 Retro Checkpoint
```
Date:
Completed:
Blocked:
Final Notes:
```

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Bedrock API rate limits | High | Low temperature, caching, retry logic |
| Playwright flakiness | Medium | Explicit waits, robust selectors, retries |
| AWS credits exhaustion | High | Use Nova Pro (cheaper), monitor usage |
| Scope creep | High | Strict MVP focus, defer Telegram to stretch |
| Demo day failures | Critical | Pre-recorded backup video, mock-only demo |

---

## Daily Standup Template

```
Date: YYYY-MM-DD
Sprint: X / Day Y

Yesterday:
- 

Today:
- 

Blockers:
- 

Notes:
- 
```
