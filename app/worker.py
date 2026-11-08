"""Run persistent workspace jobs with one active worker per SQLite database."""
from __future__ import annotations

import fcntl
import json
import logging
from pathlib import Path
import time

from . import code_changes, jobs, pr_review
from .main import DB_PATH, db, get_task, model_text, run_task

log = logging.getLogger(__name__)


def process_one():
    with db() as conn:
        job = jobs.claim(conn)
    if not job:
        return False
    try:
        task = get_task(job["task_id"])
        if job["kind"] == "proposal" and task["status"] == "pending_review":
            # A prior worker may have committed the proposal before recording job completion.
            result = None
        elif task["updated_at"] != job["task_version"]:
            raise code_changes.CodeJobError("The task changed after it was queued.")
        elif job["kind"] == "proposal":
            run_task(task["id"], queued_job_id=job["id"])
            result = None
        elif task["status"] == "approved" and task["domain"] == "engineering":
            if job["revision"]:
                result = code_changes.revise(task, job["id"], job["target_repo"],
                                             json.loads(job["revision"]), model_text)
            else:
                result = code_changes.publish(task, job["id"], job["target_repo"], model_text)
        else:
            raise code_changes.CodeJobError("Code changes require an approved engineering task.")
    except Exception as exc:
        error = str(exc) if isinstance(exc, code_changes.CodeJobError) else (
            f"{type(exc).__name__}: job failed. Check worker configuration and try again."
        )
        log.warning("Job %s failed: %s", job["id"], error)
        with db() as conn:
            conn.execute("UPDATE jobs SET state='failed', error=? WHERE id=?", (error, job["id"]))
    else:
        with db() as conn:
            conn.execute("UPDATE jobs SET state='done', result=? WHERE id=?", (result, job["id"]))
            if result:
                conn.execute("""INSERT INTO pr_status (task_id,url,repo) VALUES (?,?,?)
                    ON CONFLICT(task_id) DO UPDATE SET snapshot=NULL,synced_at=0,error=NULL""",
                    (job["task_id"], result, job["target_repo"]))
    return True


def sync_one():
    with db() as conn:
        pr = conn.execute("""SELECT * FROM pr_status WHERE synced_at < ?
            ORDER BY synced_at LIMIT 1""", (time.time() - 60,)).fetchone()
    if pr is None:
        return
    try:
        snapshot = pr_review.review(Path.cwd(), pr["repo"], pr["url"])
    except Exception:
        error = "GitHub sync failed. Check worker authentication and repository permissions."
        with db() as conn:
            conn.execute("UPDATE pr_status SET synced_at=?,error=? WHERE task_id=?",
                         (time.time(), error, pr["task_id"]))
    else:
        with db() as conn:
            conn.execute("UPDATE pr_status SET snapshot=?,synced_at=?,error=NULL WHERE task_id=?",
                         (json.dumps(snapshot), time.time(), pr["task_id"]))


def main():
    logging.basicConfig(level=logging.INFO)
    lock_path = DB_PATH.resolve().with_suffix(DB_PATH.suffix + ".worker.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker is already running for this database.") from None
        with db() as conn:
            conn.execute("UPDATE jobs SET state='queued' WHERE state='running'")
        log.info("Watching the workspace queue")
        while True:
            processed = process_one()
            sync_one()
            if not processed:
                time.sleep(2)


if __name__ == "__main__":
    main()
