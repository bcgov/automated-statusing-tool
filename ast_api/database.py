import json
import sqlite3

from shared_models.models import CreateJob, JobStatus


def create_connection():
    return sqlite3.connect("jobs.db")


def create_table():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, 
            email TEXT NOT NULL,
            region TEXT NOT NULL,
            source TEXT NOT NULL DEFAULT '1',
            crown_file_number TEXT,
            disposition_number TEXT,
            parcel_number TEXT,
            generate_maps BOOLEAN DEFAULT FALSE,
            export_overlap_results BOOLEAN DEFAULT FALSE,
            status TEXT NOT NULL
                CHECK (status IN ('Queued', 'Processing', 'Publishing', 'Completed', 'Failed'))
        )
        """
    )
    columns = {
        row[1] for row in cursor.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "source" not in columns:
        cursor.execute(
            "ALTER TABLE jobs ADD COLUMN source TEXT NOT NULL DEFAULT '1'"
        )
    connection.commit()
    connection.close()


def create_job(job: CreateJob) -> int:
    data = job.model_dump(mode="json")

    row = {
        "name": data["name"],
        "email": data["email"],
        "region": data["region"].value if hasattr(data["region"], "value") else str(data["region"]),
        "source": data["source"],
        "crown_file_number": data["crown_file_number"],
        "disposition_number": data["disposition_number"],
        "parcel_number": data["parcel_number"],
        "generate_maps": data["generate_maps"],
        "export_overlap_results": data["export_overlap_results"],
        "status": (job.status or JobStatus.QUEUED).value,
    }

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (
            name, email, region, source, crown_file_number, disposition_number,
            parcel_number, generate_maps, export_overlap_results, status
        )
        VALUES (
            :name, :email, :region, :source, :crown_file_number,
            :disposition_number, :parcel_number, :generate_maps,
            :export_overlap_results, :status
        )
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
            name,
            email,
            region,
            source,
            crown_file_number,
            disposition_number,
            parcel_number,
            generate_maps,
            export_overlap_results,
            status
        FROM jobs
        ORDER BY job_id DESC
        """
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs
