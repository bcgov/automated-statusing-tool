import json
from pathlib import Path
import sqlite3


from shared_models.models import CreateJob, JobStatus

#create path anchored to the current file's directory
DB_PATH = Path(__file__).resolve().parent / "jobs.db"

def create_connection():
    return sqlite3.connect(DB_PATH)


def create_table():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            body TEXT NOT NULL, 
            status TEXT NOT NULL
                CHECK (status IN ('Queued', 'Processing', 'Publishing', 'Completed', 'Failed'))
        )
        """
    )
    connection.commit()
    connection.close()


def create_job(job: CreateJob) -> int:
    data = job.model_dump(mode="json")

    row = {
        "body": json.dumps(data),
        "status": (job.status or JobStatus.QUEUED).value,
    }

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (body, status)
        VALUES (:body, :status)
        """,
        row,
    )
    conn.commit()
    job_id = int(cursor.lastrowid)
    conn.close()
    return job_id


def get_jobs():
    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            job_id,
            status

        FROM jobs
        ORDER BY job_id DESC
        """
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs
