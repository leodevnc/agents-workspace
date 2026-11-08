# Agents Workspace

Run a local review inbox for a chief-of-staff agent and domain leads.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Requires Python 3.11+. Open http://127.0.0.1:8000.

1. Create a task, select a domain and priority, and optionally attach screenshot and video URLs.
2. Generate a proposal. A specialist drafts the work, the domain lead reviews it, and the chief of staff summarizes the decision.
3. Review the recommendation and evidence. Approve or reject with optional rationale. Use **J** and **K** to jump through pending reviews, **N** to create a task, and **R** to refresh.
4. Generate a revision after rejection. Recent decisions in the same domain become context for later proposals.

The default demo runs locally with deterministic output. Set `OPENAI_API_KEY` in your environment to enable OpenAI Responses API calls and optionally set `OPENAI_MODEL` to override the default. Task text and recent decision notes are sent to the model when enabled. Evidence URLs stay in the inbox.

SQLite stores tasks, evidence links, and decisions under `data/`. Override the database path with `CHIEF_DB_PATH`. Use the localhost binding for this single-user app. Approvals record decisions. Agent runs are user-triggered, and evidence is provided by URL. Always-on workers, repository actions, automatic media capture, and voice review are future work.

```bash
python -m pytest -q
```

Inspired by [Brian Armstrong's agent workflow](https://x.com/brian_armstrong/status/2119112609223827547).
