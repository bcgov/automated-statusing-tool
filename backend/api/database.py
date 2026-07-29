import sqlite3

from models import JobCreate

def create_connection():
    connection = sqlite3.connect("jobs.db")
    return connection

def create_table():
    connection = create_connection()
    cursor = connection.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        status TEXT NOT NULL
        )
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