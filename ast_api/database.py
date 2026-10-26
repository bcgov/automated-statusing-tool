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
            user TEXT NOT NULL,
            date TEXT NOT NULL,
            region TEXT NOT NULL,
            area_of_interest TEXT NOT NULL,
            crown_file_number TEXT,
            disposition_number TEXT,
            parcel_number TEXT,
            output_directory TEXT NOT NULL,
            retain_existing_outputs INTEGER NOT NULL DEFAULT 0,
            suppress_tab_3 INTEGER NOT NULL DEFAULT 0,
            suppress_map_creation INTEGER NOT NULL DEFAULT 0,
            open_output_directory_on_completion INTEGER NOT NULL DEFAULT 0,
            enable_portable_spreadsheet INTEGER NOT NULL DEFAULT 0,
            registries TEXT NOT NULL,
            aoi_id TEXT NOT NULL,
            aoi_name TEXT NOT NULL,
            aoi TEXT NOT NULL,
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
        "user": data["user"],
        "date": data["date"],
        "region": data["region"].value if hasattr(data["region"], "value") else str(data["region"]),
        "area_of_interest": data["area_of_interest"],
        "crown_file_number": data["crown_file_number"],
        "disposition_number": data["disposition_number"],
        "parcel_number": data["parcel_number"],
        "output_directory": data["output_directory"],
        "retain_existing_outputs": int(data["retain_existing_outputs"]),
        "suppress_tab_3": int(data["suppress_tab_3"]),
        "suppress_map_creation": int(data["suppress_map_creation"]),
        "open_output_directory_on_completion": int(data["open_output_directory_on_completion"]),
        "enable_portable_spreadsheet": int(data["enable_portable_spreadsheet"]),
        "registries": json.dumps(data["registries"]),
        "aoi_id": data["aoi_id"],
        "aoi_name": data["aoi_name"],
        "aoi": json.dumps(data["aoi"]),
        "status": (job.status or JobStatus.QUEUED).value,
    }

    conn = create_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO jobs (
            user, date, region, area_of_interest, crown_file_number, disposition_number,
            parcel_number, output_directory, retain_existing_outputs, suppress_tab_3,
            suppress_map_creation, open_output_directory_on_completion,
            enable_portable_spreadsheet, registries, aoi_id, aoi_name, aoi, status
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        tuple(row.values()),
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
            user,
            date,
            region,
            status
        FROM jobs
        ORDER BY job_id DESC
        """
    )
    jobs = cursor.fetchall()
    conn.close()
    return jobs

