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

SQLite stores tasks, evidence links, and decisions under `data/`. Override the database path with `CHIEF_DB_PATH`. Use the localhost binding for this single-user app. Approvals record decisions. The default mode runs proposals on demand. Background jobs and PR evidence can be enabled as described below.

```bash
python -m pytest -q
```

Inspired by [Brian Armstrong's agent workflow](https://x.com/brian_armstrong/status/2119112609223827547).

## Background worker and Draft PRs

Set `CHIEF_BACKGROUND_JOBS=1` in both the web app and worker environments, then
run `python -m app.worker` as a separate process. Both processes must use the
same SQLite path. The worker requires Linux or macOS, processes jobs in priority
order, and resumes interrupted jobs on restart. Rejected proposals and failed
jobs can be retried from the inbox. Operators should run `gh auth status` before starting the worker to verify authentication and confirm that the GitHub identity has write access to the target repository.

To enable code jobs, set `CHIEF_GITHUB_REPO=owner/repo` in both processes, and
configure the worker with `OPENAI_API_KEY`, `CHIEF_CODE_FILES` (a JSON array of
up to eight existing source files), Git, and authenticated `gh` with repository
write and PR access. For example, `CHIEF_CODE_FILES='["app/static/index.html"]'`.
Only configure source files you are permitted to send to the model. Repository
files and approved proposals are included in code requests. Keep credentials
in your local environment or secret manager.

1. Create an engineering task. The worker generates a proposal automatically.
2. Approve the proposal, then select **Generate changes and open Draft PR**.
3. Open the Draft PR from the inbox. Inspect the diff and CI results before
   marking ready. This repository's **Review evidence** workflow exercises the
   browser flow and uploads a screenshot and video as Actions artifacts.

The worker restricts edits to the configured regular files. It uses Git objects
without checking out or executing generated code locally. For a different target
repository, install an appropriate test and capture workflow first. The
included workflow records a fixed review flow on this app. Use GitHub branch
protection to enforce CI and human review before merging.

### Review GitHub results in the inbox

The worker refreshes each PR about once per minute and stores the latest CI
checks, requested reviewers, recent submitted reviews, and available
`review-evidence` artifacts in SQLite. Its GitHub identity needs read access to
Actions artifacts. Open a task's pull request panel to inspect the results.
For a revision, enter the instructions and select **Generate revision in this
PR**. The worker writes to the original workspace branch only if it still
matches the reviewed commit. A revision is a separate request and reruns CI
on the same PR. Review the updated diff on GitHub before merging.
