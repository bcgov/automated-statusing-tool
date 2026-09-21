import sqlite3
from shared_models.models import CreateJob



def create_connection():
    connection = sqlite3.connect("jobs.db")
    return connection

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

            area_of_interest TEXT,
            crown_file_number TEXT,
            disposition_number TEXT,
            parcel_number TEXT,

            output_directory TEXT NOT NULL,

            retain_existing_outputs INTEGER NOT NULL DEFAULT 0,
            suppress_tab_3 INTEGER NOT NULL DEFAULT 0,
            suppress_map_creation INTEGER NOT NULL DEFAULT 0,
            open_output_directory_on_completion INTEGER NOT NULL DEFAULT 0,
            enable_portable_spreadsheet INTEGER NOT NULL DEFAULT 0,

            status TEXT NOT NULL
                CHECK (status IN ('Pending', 'Running', 'Completed', 'Failed'))
        )
        """
    )
    connection.commit()
    connection.close()

def create_job(job: CreateJob):
    connection = create_connection()
    cursor = connection.cursor()

    data = job.model_dump(exclude={"job_id"})

    columns = ", ".join(data.keys())
    placeholders = ", ".join(["?"] * len(data))

    cursor.execute(
        f"INSERT INTO jobs ({columns}) VALUES ({placeholders})",
        tuple(data.values())
    )
    connection.commit()
    job_id = cursor.lastrowid
    connection.close()
    return job_id

def get_jobs():
    connection = create_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            job_id,
            user,
            date,
            region,
            status
        FROM jobs
    """)

    jobs = cursor.fetchall()

    connection.close()

    return jobs

