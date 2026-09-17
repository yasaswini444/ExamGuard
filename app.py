from flask import (
    Flask,
    request,
    render_template,
    session,
    redirect
)

from database import init_db, get_db

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from camera import save_captured_photo

from monitoring.face_logger import log_face_state

from monitoring.face_monitoring import detect_face

import os
import sqlite3
import uuid

from datetime import datetime


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(__name__)

# Secret key used for Flask sessions
app.secret_key = "exam_guard_key"

# Folder where candidate photos are stored
upload_folder = "static/uploads"


# ============================================================
# INITIALIZE DATABASE
# ============================================================

init_db()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return "Welcome to Exam Guard"


# ============================================================
# CAPTURE CANDIDATE PHOTO
# ============================================================

@app.route("/capture-photo", methods=["POST"])
def capture_candidate_photo():

    # Get photo uploaded from browser
    photo = request.files.get("photo")

    # Check whether photo was received
    if not photo:

        return {
            "success": False,
            "message": "No photo uploaded"
        }, 400

    # Convert uploaded photo into bytes
    image_data = photo.read()

    # Save photo using camera.py
    photo_path = save_captured_photo(
        image_data
    )

    # Check whether photo was successfully saved
    if not photo_path:

        return {
            "success": False,
            "message": "Could not process photo"
        }, 400

    # Store photo path temporarily in session
    # Registration will use this path
    session["capture_photo"] = photo_path

    return {
        "success": True,
        "message": "Photo captured successfully",
        "photo_path": photo_path
    }, 200


# ============================================================
# REGISTER
# ============================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    # --------------------------------------------------------
    # SHOW REGISTER PAGE
    # --------------------------------------------------------

    if request.method == "GET":

        return render_template(
            "register.html"
        )

    # --------------------------------------------------------
    # GET FORM DATA
    # --------------------------------------------------------

    name = request.form.get(
        "name",
        ""
    ).strip()

    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # --------------------------------------------------------
    # VALIDATE FORM DATA
    # --------------------------------------------------------

    if not name or not email or not password:

        return render_template(
            "register.html",
            error="Please fill in all required fields"
        )

    # --------------------------------------------------------
    # GET CAPTURED PHOTO
    # --------------------------------------------------------

    photo_path = session.get(
        "capture_photo"
    )

    if not photo_path:

        return render_template(
            "register.html",
            error="Please capture your photo before registering"
        )

    # --------------------------------------------------------
    # HASH PASSWORD
    # --------------------------------------------------------

    hashed_password = generate_password_hash(
        password
    )

    connection = None

    try:

        # ----------------------------------------------------
        # CONNECT TO DATABASE
        # ----------------------------------------------------

        connection = get_db()

        # ----------------------------------------------------
        # INSERT CANDIDATE
        # ----------------------------------------------------

        connection.execute(
            """
            INSERT INTO candidates
            (
                name,
                email,
                password,
                photo
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                name,
                email,
                hashed_password,
                photo_path
            )
        )

        # ----------------------------------------------------
        # SAVE DATABASE CHANGES
        # ----------------------------------------------------

        connection.commit()

        print(
            f"Registration successful for: {name}"
        )

    # --------------------------------------------------------
    # DUPLICATE EMAIL
    # --------------------------------------------------------

    except sqlite3.IntegrityError:

        # Delete captured photo
        if os.path.exists(photo_path):

            os.remove(photo_path)

        # Remove photo from session
        session.pop(
            "capture_photo",
            None
        )

        return render_template(
            "register.html",
            error="Email already registered. Please use a different email."
        )

    # --------------------------------------------------------
    # OTHER DATABASE ERROR
    # --------------------------------------------------------

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Registration error:",
            e
        )

        return render_template(
            "register.html",
            error="Registration failed. Please try again."
        )

    # --------------------------------------------------------
    # CLOSE DATABASE
    # --------------------------------------------------------

    finally:

        if connection:

            connection.close()

    # --------------------------------------------------------
    # REMOVE TEMPORARY PHOTO FROM SESSION
    # --------------------------------------------------------

    session.pop(
        "capture_photo",
        None
    )

    # --------------------------------------------------------
    # REDIRECT TO LOGIN
    # --------------------------------------------------------

    return redirect(
        "/login"
    )


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    # --------------------------------------------------------
    # SHOW LOGIN PAGE
    # --------------------------------------------------------

    if request.method == "GET":

        return render_template(
            "login.html"
        )

    # --------------------------------------------------------
    # GET LOGIN FORM DATA
    # --------------------------------------------------------

    email = request.form.get(
        "email",
        ""
    ).strip()

    password = request.form.get(
        "password",
        ""
    )

    # --------------------------------------------------------
    # VALIDATE INPUT
    # --------------------------------------------------------

    if not email or not password:

        return render_template(
            "login.html",
            error="Please enter email and password"
        )

    connection = None
    candidate = None

    try:

        # ----------------------------------------------------
        # CONNECT TO DATABASE
        # ----------------------------------------------------

        connection = get_db()

        # ----------------------------------------------------
        # FIND CANDIDATE
        # ----------------------------------------------------

        candidate = connection.execute(
            """
            SELECT *
            FROM candidates
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

    except Exception as e:

        print(
            "Login error:",
            e
        )

        return render_template(
            "login.html",
            error="Login failed. Please try again."
        )

    finally:

        if connection:

            connection.close()

    # --------------------------------------------------------
    # CHECK PASSWORD
    # --------------------------------------------------------

    if candidate and check_password_hash(
        candidate["password"],
        password
    ):

        # Store candidate ID in session
        session["candidate_id"] = candidate["id"]

        return redirect(
            "/dashboard"
        )

    # --------------------------------------------------------
    # INVALID LOGIN
    # --------------------------------------------------------

    return render_template(
        "login.html",
        error="Invalid email or password"
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    # --------------------------------------------------------
    # CHECK WHETHER CANDIDATE IS LOGGED IN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return "Please login first", 401

    # --------------------------------------------------------
    # SHOW DASHBOARD
    # --------------------------------------------------------

    return render_template(
        "dashboard.html"
    )


# ============================================================
# START EXAM
# ============================================================

@app.route("/start-exam")
def start_exam():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return {
            "success": False,
            "message": "Candidate is not logged in"
        }, 401

    # --------------------------------------------------------
    # CREATE UNIQUE EXAM SESSION ID
    # --------------------------------------------------------

    exam_session_id = str(
        uuid.uuid4()
    )

    # Store exam session ID
    session["exam_session_id"] = exam_session_id

    print(
        f"Exam started: {exam_session_id}"
    )

    # --------------------------------------------------------
    # OPEN EXAM PAGE
    # --------------------------------------------------------

    return render_template(
        "exam.html"
    )


# ============================================================
# FACE MONITORING
# ============================================================

@app.route("/monitor-face", methods=["POST"])
def monitor_face():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return {
            "success": False,
            "message": "Candidate is not logged in"
        }, 401

    candidate_id = session[
        "candidate_id"
    ]

    # --------------------------------------------------------
    # GET EXAM SESSION
    # --------------------------------------------------------

    exam_session_id = session.get(
        "exam_session_id"
    )

    if not exam_session_id:

        return {
            "success": False,
            "message": "Exam not started"
        }, 400

    # --------------------------------------------------------
    # GET IMAGE FROM BROWSER
    # --------------------------------------------------------

    image = request.files.get(
        "image"
    )

    if not image:

        return {
            "success": False,
            "message": "No image received"
        }, 400

    # --------------------------------------------------------
    # READ IMAGE
    # --------------------------------------------------------

    image_data = image.read()

    if not image_data:

        return {
            "success": False,
            "message": "Empty image received"
        }, 400

    # --------------------------------------------------------
    # DETECT FACE
    # --------------------------------------------------------

    try:

        face_present, processed_image = detect_face(
            image_data
        )

    except Exception as e:

        print(
            "Face detection error:",
            e
        )

        return {
            "success": False,
            "message": "Face detection failed"
        }, 500

    # --------------------------------------------------------
    # DETERMINE FACE STATE
    # --------------------------------------------------------

    if face_present:

        current_state = "face_detected"

    else:

        current_state = "face_absent"

    # --------------------------------------------------------
    # LOG FACE STATE
    # --------------------------------------------------------

    try:

        log_face_state(
            candidate_id,
            exam_session_id,
            current_state
        )

    except Exception as e:

        print(
            "Face logging error:",
            e
        )

        return {
            "success": False,
            "message": "Could not log face state"
        }, 500

    # --------------------------------------------------------
    # RETURN RESULT TO BROWSER
    # --------------------------------------------------------

    return {
        "success": True,
        "state": current_state
    }, 200


# ============================================================
# LOG BROWSER EVENT
# ============================================================

@app.route("/log-browser-event", methods=["POST"])
def log_browser_event():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return {
            "success": False,
            "message": "Candidate is not logged in"
        }, 401

    candidate_id = session[
        "candidate_id"
    ]

    # --------------------------------------------------------
    # GET EXAM SESSION
    # --------------------------------------------------------

    exam_session_id = session.get(
        "exam_session_id"
    )

    if not exam_session_id:

        return {
            "success": False,
            "message": "Exam not started"
        }, 400

    # --------------------------------------------------------
    # GET JSON DATA
    # --------------------------------------------------------

    data = request.get_json()

    if not data or "event" not in data:

        return {
            "success": False,
            "message": "No event data received"
        }, 400

    # --------------------------------------------------------
    # GET EVENT TYPE
    # --------------------------------------------------------

    event_type = data.get(
        "event",
        ""
    )

    details = data.get(
        "details",
        ""
    )

    # Make sure event is a string
    if not isinstance(event_type, str):

        return {
            "success": False,
            "message": "Invalid event type"
        }, 400

    event_type = event_type.strip()

    # --------------------------------------------------------
    # VALIDATE EVENT
    # --------------------------------------------------------

    if not event_type:

        return {
            "success": False,
            "message": "Event type is required"
        }, 400

    connection = None

    try:

        # ----------------------------------------------------
        # CONNECT TO DATABASE
        # ----------------------------------------------------

        connection = get_db()

        # ----------------------------------------------------
        # INSERT BROWSER EVENT
        # ----------------------------------------------------

        connection.execute(
            """
            INSERT INTO browser_events
            (
                candidate_id,
                session_id,
                event_type,
                event_time,
                details
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                exam_session_id,
                event_type,
                datetime.now().isoformat(),
                details
            )
        )

        # ----------------------------------------------------
        # SAVE CHANGES
        # ----------------------------------------------------

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Browser event error:",
            e
        )

        return {
            "success": False,
            "message": str(e)
        }, 500

    finally:

        if connection:

            connection.close()

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    return {
        "success": True,
        "message": "Browser event saved"
    }, 200


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    # Clear login session
    # Also removes exam_session_id
    session.clear()

    return redirect(
        "/login"
    )


# ============================================================
# RUN APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )