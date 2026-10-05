
import sqlite3
import os


DATABASE = "database/examguard.db"


# ----------------------------------------
# DATABASE CONNECTION
# ----------------------------------------
def get_db():

    connection = sqlite3.connect(DATABASE)

    # Allows dictionary-style access:
    # candidate["id"]
    # candidate["name"]
    # candidate["email"]
    # candidate["password"]
    # candidate["photo"]
    # candidate["created_at"]

    connection.row_factory = sqlite3.Row

    return connection


# ----------------------------------------
# INITIALIZE DATABASE
# ----------------------------------------
def init_db():

    # Create database folder if it does not exist
    os.makedirs("database", exist_ok=True)

    connection = get_db()

    try:

        # ----------------------------------------
        # CANDIDATES TABLE
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS candidates (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                email TEXT NOT NULL UNIQUE,

                password TEXT NOT NULL,

                photo TEXT,

                created_at TEXT
            )
        """)


        # ----------------------------------------
        # CHECK CREATED_AT COLUMN
        # ----------------------------------------
        # Protects an older existing database.
        # If created_at already exists, nothing happens.
        # If it does not exist, the column is added.

        columns = connection.execute(
            "PRAGMA table_info(candidates)"
        ).fetchall()

        column_names = [
            column["name"]
            for column in columns
        ]

        if "created_at" not in column_names:

            connection.execute(
                "ALTER TABLE candidates ADD COLUMN created_at TEXT"
            )


        # ----------------------------------------
        # FACE MONITORING EVENTS
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS face_events (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                candidate_id INTEGER NOT NULL,

                session_id TEXT NOT NULL,

                event_type TEXT NOT NULL,

                started_at TEXT NOT NULL,

                ended_at TEXT,

                duration_seconds REAL,

                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
            )
        """)


        # ----------------------------------------
        # BROWSER ACTIVITY EVENTS
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS browser_events (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                candidate_id INTEGER NOT NULL,

                session_id TEXT NOT NULL,

                event_type TEXT NOT NULL,

                event_time TEXT NOT NULL,

                details TEXT,

                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
            )
        """)


        # ----------------------------------------
        # SUSPICIOUS EVENTS
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS suspicious_events (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                candidate_id INTEGER NOT NULL,

                session_id TEXT NOT NULL,

                event_type TEXT NOT NULL,

                reason TEXT NOT NULL,

                event_time TEXT NOT NULL,

                severity TEXT NOT NULL,

                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
            )
        """)


        # ----------------------------------------
        # EXAM SESSIONS
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS exam_sessions (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                candidate_id INTEGER NOT NULL,

                session_id TEXT UNIQUE NOT NULL,

                status TEXT NOT NULL DEFAULT 'in_progress',

                started_at TEXT NOT NULL,

                paused_at TEXT,

                resumed_at TEXT,

                submitted_at TEXT,

                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
            )
        """)


        # ----------------------------------------
        # INTEGRITY SCORES
        # ----------------------------------------
        connection.execute("""
            CREATE TABLE IF NOT EXISTS integrity_scores (

                id INTEGER PRIMARY KEY AUTOINCREMENT,

                session_id TEXT UNIQUE NOT NULL,

                candidate_id INTEGER NOT NULL,

                event_penalty REAL NOT NULL,

                face_presence_ratio REAL NOT NULL,

                integrity_score REAL NOT NULL,

                risk_level TEXT NOT NULL,

                computed_at TEXT NOT NULL,

                FOREIGN KEY (candidate_id)
                    REFERENCES candidates(id)
            )
        """)


        # ----------------------------------------
        # SAVE DATABASE CHANGES
        # ----------------------------------------
        connection.commit()


        # ----------------------------------------
        # CHECK SUSPICIOUS EVENTS
        # ----------------------------------------
        # IMPORTANT:
        # The connection is still OPEN here.
        # Therefore SELECT works correctly.

        result = connection.execute(
            "SELECT * FROM suspicious_events"
        ).fetchall()

        print("Number of suspicious event rows:", len(result))

        for row in result:
            print(dict(row))


    except Exception as e:

        # If something goes wrong, undo
        # uncommitted database changes.

        connection.rollback()

        print("Database initialization error:", e)

        raise


    finally:

        # Close the connection only after
        # all database operations are finished.

        connection.close()


# ----------------------------------------
# RUN INITIALIZATION
# ----------------------------------------
if __name__ == "__main__":
    init_db()