from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import sqlite3
from ast_api.config import settings
from .models import CreateJobs

def create_connection():
    connection = sqlite3.connect("jobs.db")
    return connection

def create_table():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            job_id TEXT PRIMARY KEY,
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
        """
    )
    connection.commit()
    connection.close()

def create_job(status):
    connection = sqlite3.connect("jobs.db")
    cursor = connection.cursor()
    cursor.execute("INSERT INTO jobs (status) VALUES (?)", (status,))
    connection.commit()
    connection.close()

def get_jobs():
    connection = sqlite3.connect("jobs.db")
    cursor = connection.cursor()
    cursor.execute("SELECT id, status FROM jobs")
    jobs = cursor.fetchall()
    connection.close

    return jobs

#create_table()