"""Persistent queue shared by the web app and a single background worker."""
from __future__ import annotations

from uuid import uuid4


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, task_id INTEGER NOT NULL REFERENCES tasks(id),
        kind TEXT NOT NULL CHECK(kind IN ('proposal', 'code')),
        state TEXT NOT NULL CHECK(state IN ('queued', 'running', 'done', 'failed')),
        task_version TEXT NOT NULL, target_repo TEXT, result TEXT, error TEXT
    )""")
    if "target_repo" not in {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}:
        conn.execute("ALTER TABLE jobs ADD COLUMN target_repo TEXT")
    if "revision" not in {row["name"] for row in conn.execute("PRAGMA table_info(jobs)")}:
        conn.execute("ALTER TABLE jobs ADD COLUMN revision TEXT")
    conn.execute("""CREATE TABLE IF NOT EXISTS pr_status (
        task_id INTEGER PRIMARY KEY REFERENCES tasks(id), url TEXT NOT NULL,
        repo TEXT NOT NULL, snapshot TEXT, synced_at REAL NOT NULL DEFAULT 0, error TEXT
    )""")
    conn.execute("""INSERT OR IGNORE INTO pr_status (task_id,url,repo)
        SELECT task_id,result,target_repo FROM jobs
        WHERE kind='code' AND state='done' AND result IS NOT NULL AND target_repo IS NOT NULL""")
    conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS active_job
        ON jobs(task_id) WHERE state IN ('queued', 'running')""")


def enqueue(conn, task, kind, target_repo=None, revision=None):
    job_id = uuid4().hex
    conn.execute(
        "INSERT INTO jobs (id,task_id,kind,state,task_version,target_repo,revision) VALUES (?,?,?,'queued',?,?,?)",
        (job_id, task["id"], kind, task["updated_at"], target_repo, revision),
    )
    return job_id


def claim(conn):
    conn.execute("BEGIN IMMEDIATE")
    job = conn.execute("""SELECT j.* FROM jobs j JOIN tasks t ON t.id=j.task_id
        WHERE j.state='queued' ORDER BY t.priority, j.rowid LIMIT 1""").fetchone()
    if job:
        conn.execute("UPDATE jobs SET state='running', error=NULL WHERE id=?", (job["id"],))
    return dict(job) if job else None
