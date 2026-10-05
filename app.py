import sqlite3
import uuid

from datetime import datetime

from flask import (
    Flask,
    redirect,
    render_template,
    request,
    session,
    url_for,
    jsonify
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from database import init_db, get_db
from camera import save_captured_photo

from monitoring.face_monitoring import detect_face
from monitoring.face_logger import log_face_state

from monitoring import eventdetector

from monitoring.integrity_score import compute_integrity_score


# ============================================================
# FLASK APPLICATION
# ============================================================

app = Flask(__name__)

app.secret_key = "examguard-secret-key"


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

init_db()


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    # If candidate is already logged in,
    # directly open dashboard.

    if "candidate_id" in session:

        return redirect(
            url_for("dashboard")
        )

    return redirect(
        url_for("login")
    )


# ============================================================
# REGISTER
# ============================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
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
    ).strip().lower()

    password = request.form.get(
        "password",
        ""
    )

    # --------------------------------------------------------
    # VALIDATE FORM
    # --------------------------------------------------------

    if not name or not email or not password:

        return render_template(
            "register.html",
            error="Please fill in every field."
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
            error="Please capture your photo before registering."
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
        # SAVE
        # ----------------------------------------------------

        connection.commit()

        # Remove temporary photo information
        # from Flask session.

        session.pop(
            "capture_photo",
            None
        )

        return redirect(
            url_for(
                "login",
                registered=1
            )
        )

    # --------------------------------------------------------
    # DUPLICATE EMAIL
    # --------------------------------------------------------

    except sqlite3.IntegrityError:

        if connection:

            connection.rollback()

        return render_template(
            "register.html",
            error="An account with this email already exists."
        )

    # --------------------------------------------------------
    # OTHER ERROR
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

    finally:

        if connection:

            connection.close()


# ============================================================
# CAPTURE PHOTO
# ============================================================

@app.route(
    "/capture-photo",
    methods=["POST"]
)
def capture_candidate_photo():

    # --------------------------------------------------------
    # GET PHOTO
    # --------------------------------------------------------

    photo = request.files.get(
        "photo"
    )

    if not photo:

        return jsonify({
            "success": False,
            "message": "No photo received"
        }), 400

    # --------------------------------------------------------
    # READ IMAGE
    # --------------------------------------------------------

    image_data = photo.read()

    if not image_data:

        return jsonify({
            "success": False,
            "message": "Empty photo received"
        }), 400

    # --------------------------------------------------------
    # SAVE PHOTO
    # --------------------------------------------------------

    photo_path = save_captured_photo(
        image_data
    )

    if not photo_path:

        return jsonify({
            "success": False,
            "message": "Could not process photo"
        }), 400

    # --------------------------------------------------------
    # STORE PHOTO PATH IN SESSION
    # --------------------------------------------------------

    session["capture_photo"] = photo_path

    return jsonify({
        "success": True,
        "message": "Photo captured successfully",
        "photo_path": photo_path
    })


# ============================================================
# LOGIN
# ============================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    # --------------------------------------------------------
    # PROCESS LOGIN
    # --------------------------------------------------------

    if request.method == "POST":

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

        if not email or not password:

            return render_template(
                "login.html",
                error="Please enter email and password."
            )

        connection = None

        try:

            # ------------------------------------------------
            # DATABASE CONNECTION
            # ------------------------------------------------

            connection = get_db()

            # ------------------------------------------------
            # FIND CANDIDATE
            # ------------------------------------------------

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

        # ----------------------------------------------------
        # VERIFY PASSWORD
        # ----------------------------------------------------

        if (
            candidate
            and check_password_hash(
                candidate["password"],
                password
            )
        ):

            # Store candidate information
            # in Flask session.

            session["candidate_id"] = (
                candidate["id"]
            )

            session["candidate_name"] = (
                candidate["name"]
            )

            return redirect(
                url_for("dashboard")
            )

        # ----------------------------------------------------
        # INVALID LOGIN
        # ----------------------------------------------------

        return render_template(
            "login.html",
            error="Invalid email or password."
        )

    # --------------------------------------------------------
    # GET LOGIN PAGE
    # --------------------------------------------------------

    registered = request.args.get(
        "registered"
    )

    return render_template(
        "login.html",
        registered=registered
    )


# ============================================================
# DASHBOARD
# ============================================================

@app.route("/dashboard")
def dashboard():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return redirect(
            url_for("login")
        )

    candidate_id = session[
        "candidate_id"
    ]

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # GET CANDIDATE
        # ----------------------------------------------------

        candidate = connection.execute(
            """
            SELECT *
            FROM candidates
            WHERE id = ?
            """,
            (candidate_id,)
        ).fetchone()

        # Candidate no longer exists

        if not candidate:

            session.clear()

            return redirect(
                url_for("login")
            )

        # ----------------------------------------------------
        # GET RECENT EXAM SESSIONS
        # ----------------------------------------------------

        recent_sessions = connection.execute(
            """
            SELECT
                session_id,
                status,
                started_at,
                submitted_at
            FROM exam_sessions
            WHERE candidate_id = ?
            ORDER BY started_at DESC
            LIMIT 5
            """,
            (candidate_id,)
        ).fetchall()

        # ----------------------------------------------------
        # SEND DATA TO DASHBOARD
        # ----------------------------------------------------

        return render_template(
            "dashboard.html",
            candidate=candidate,
            recent_sessions=recent_sessions
        )

    except Exception as e:

        print(
            "Dashboard error:",
            e
        )

        return render_template(
            "dashboard.html"
        )

    finally:

        if connection:

            connection.close()


# ============================================================
# START EXAM
# ============================================================

@app.route("/start-exam")
def start_exam():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return redirect(
            url_for("login")
        )

    # --------------------------------------------------------
    # CREATE UNIQUE EXAM SESSION
    # --------------------------------------------------------

    exam_session_id = str(
        uuid.uuid4()
    )

    session["exam_session_id"] = (
        exam_session_id
    )

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # INSERT EXAM SESSION
        # ----------------------------------------------------

        connection.execute(
            """
            INSERT INTO exam_sessions
            (
                candidate_id,
                session_id,
                status,
                started_at
            )
            VALUES (?, ?, 'in_progress', ?)
            """,
            (
                session["candidate_id"],
                exam_session_id,
                datetime.now().isoformat()
            )
        )

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Start exam error:",
            e
        )

        session.pop(
            "exam_session_id",
            None
        )

        return jsonify({
            "success": False,
            "message": "Could not start examination"
        }), 500

    finally:

        if connection:

            connection.close()

    # --------------------------------------------------------
    # OPEN EXAM PAGE
    # --------------------------------------------------------

    return render_template(
        "exam.html",
        candidate_name=session.get(
            "candidate_name"
        )
    )


# ============================================================
# PAUSE EXAM
# ============================================================

@app.route(
    "/pause-exam",
    methods=["POST"]
)
def pause_exam():

    # --------------------------------------------------------
    # CHECK ACTIVE SESSION
    # --------------------------------------------------------

    if (
        "candidate_id" not in session
        or "exam_session_id" not in session
    ):

        return jsonify({
            "success": False,
            "message": "No active exam session"
        }), 400

    candidate_id = session[
        "candidate_id"
    ]

    exam_session_id = session[
        "exam_session_id"
    ]

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # PAUSE EXAM
        # ----------------------------------------------------

        connection.execute(
            """
            UPDATE exam_sessions
            SET
                status = 'paused',
                paused_at = ?
            WHERE session_id = ?
            AND candidate_id = ?
            """,
            (
                datetime.now().isoformat(),
                exam_session_id,
                candidate_id
            )
        )

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Pause exam error:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Could not pause exam"
        }), 500

    finally:

        if connection:

            connection.close()

    return jsonify({
        "success": True,
        "message": "Exam paused"
    })


# ============================================================
# RESUME EXAM
# ============================================================

@app.route(
    "/resume-exam",
    methods=["POST"]
)
def resume_exam():

    # --------------------------------------------------------
    # CHECK ACTIVE SESSION
    # --------------------------------------------------------

    if (
        "candidate_id" not in session
        or "exam_session_id" not in session
    ):

        return jsonify({
            "success": False,
            "message": "No active exam session"
        }), 400

    candidate_id = session[
        "candidate_id"
    ]

    exam_session_id = session[
        "exam_session_id"
    ]

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # RESUME EXAM
        # ----------------------------------------------------

        connection.execute(
            """
            UPDATE exam_sessions
            SET
                status = 'in_progress',
                resumed_at = ?
            WHERE session_id = ?
            AND candidate_id = ?
            """,
            (
                datetime.now().isoformat(),
                exam_session_id,
                candidate_id
            )
        )

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Resume exam error:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Could not resume exam"
        }), 500

    finally:

        if connection:

            connection.close()

    return jsonify({
        "success": True,
        "message": "Exam resumed"
    })


# ============================================================
# SUBMIT EXAM
# ============================================================

@app.route(
    "/submit-exam",
    methods=["POST"]
)
def submit_exam():

    # --------------------------------------------------------
    # 1. CHECK LOGIN AND EXAM SESSION
    # --------------------------------------------------------

    if (
        "candidate_id" not in session
        or "exam_session_id" not in session
    ):

        return jsonify({
            "success": False,
            "message": "No active exam session"
        }), 400

    candidate_id = session[
        "candidate_id"
    ]

    exam_session_id = session[
        "exam_session_id"
    ]

    submitted_at = (
        datetime.now().isoformat()
    )

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # 2. CHECK EXAM SESSION
        # ----------------------------------------------------

        exam_session = connection.execute(
            """
            SELECT *
            FROM exam_sessions
            WHERE session_id = ?
            AND candidate_id = ?
            """,
            (
                exam_session_id,
                candidate_id
            )
        ).fetchone()

        if not exam_session:

            return jsonify({
                "success": False,
                "message": "Exam session not found"
            }), 404

        # ----------------------------------------------------
        # PREVENT DOUBLE SUBMISSION
        # ----------------------------------------------------

        if (
            "status" in exam_session.keys()
            and exam_session["status"] == "submitted"
        ):

            return jsonify({
                "success": False,
                "message": "Exam has already been submitted"
            }), 400

        # ----------------------------------------------------
        # 3. UPDATE EXAM SESSION
        # ----------------------------------------------------

        connection.execute(
            """
            UPDATE exam_sessions
            SET
                status = 'submitted',
                submitted_at = ?
            WHERE session_id = ?
            AND candidate_id = ?
            """,
            (
                submitted_at,
                exam_session_id,
                candidate_id
            )
        )

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Exam submission error:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Could not submit examination"
        }), 500

    finally:

        if connection:

            connection.close()

    # --------------------------------------------------------
    # 4. CALCULATE INTEGRITY SCORE
    # --------------------------------------------------------


    # --------------------------------------------------------

    try:

        result = compute_integrity_score(
            candidate_id,
            exam_session_id
        )

    except Exception as e:

        print(
            "Integrity score error:",
            e
        )

        # If scoring fails, still report
        # successful exam submission.

        result = {
            "integrity_score": None,
            "face_presence_ratio": None,
            "event_penalty": None,
            "risk_level": "NOT_CALCULATED"
        }

    # --------------------------------------------------------
    # 5. REMOVE ACTIVE EXAM SESSION
    # --------------------------------------------------------

    session.pop(
        "exam_session_id",
        None
    )

    # --------------------------------------------------------
    # 6. RETURN FINAL RESULT
    # --------------------------------------------------------

    return jsonify({
        "success": True,
        "message": "Exam submitted successfully",

        "integrity_score":
            result.get(
                "integrity_score"
            ),

        "face_presence_ratio":
            result.get(
                "face_presence_ratio"
            ),

        "event_penalty":
            result.get(
                "event_penalty"
            ),

        "risk_level":
            result.get(
                "risk_level"
            ),

        "redirect":
            url_for("dashboard")
    })


# ============================================================
# FACE MONITORING
# ============================================================

@app.route(
    "/monitor-face",
    methods=["POST"]
)
def monitor_face():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return jsonify({
            "success": False,
            "message": "Candidate not logged in"
        }), 401

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

        return jsonify({
            "success": False,
            "message": "Exam session not started"
        }), 400

    # --------------------------------------------------------
    # GET IMAGE
    #
    # Your current exam.html sends:
    # formData.append("image", blob)
    # --------------------------------------------------------

    image = request.files.get(
        "image"
    )

    if not image:

        return jsonify({
            "success": False,
            "message": "No image received"
        }), 400

    # --------------------------------------------------------
    # READ IMAGE
    # --------------------------------------------------------

    image_data = image.read()

    if not image_data:

        return jsonify({
            "success": False,
            "message": "Empty image received"
        }), 400

    # --------------------------------------------------------
    # FACE DETECTION
    #
    # Your current face_monitoring.py returns:
    #
    # (face_present, processed_image)
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

        return jsonify({
            "success": False,
            "message": "Face detection failed"
        }), 500

    # --------------------------------------------------------
    # DETERMINE STATE
    # --------------------------------------------------------

    if face_present:

        current_state = (
            "face_detected"
        )

    else:

        current_state = (
            "face_absent"
        )

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

        return jsonify({
            "success": False,
            "message": "Could not log face state"
        }), 500

    # --------------------------------------------------------
    # RETURN RESULT
    # --------------------------------------------------------

    return jsonify({
        "success": True,
        "state": current_state
    })


# ============================================================
# BROWSER EVENT LOGGING
# ============================================================

@app.route(
    "/log-browser-event",
    methods=["POST"]
)
def log_browser_event():

    # --------------------------------------------------------
    # CHECK LOGIN
    # --------------------------------------------------------

    if "candidate_id" not in session:

        return jsonify({
            "success": False,
            "message": "Candidate not logged in"
        }), 401

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

        return jsonify({
            "success": False,
            "message": "Exam session not started"
        }), 400

    # --------------------------------------------------------
    # GET JSON
    # --------------------------------------------------------

    data = request.get_json(
        silent=True
    )

    if not data:

        return jsonify({
            "success": False,
            "message": "No event data received"
        }), 400

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Your current exam.html sends:
    #
    # {
    #     event: eventType,
    #     details: details
    # }
    #
    # Therefore we use "event" here.
    # --------------------------------------------------------

    event_type = data.get(
        "event"
    )

    details = data.get(
        "details",
        ""
    )

    # --------------------------------------------------------
    # VALIDATE EVENT
    # --------------------------------------------------------

    if not event_type:

        return jsonify({
            "success": False,
            "message": "Event type is required"
        }), 400

    connection = None

    try:

        connection = get_db()

        # ----------------------------------------------------
        # SAVE BROWSER EVENT
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
        # RUN RULE-BASED EVENT DETECTOR
        # ----------------------------------------------------

        eventdetector.evaluate_browser_event(
            connection,
            candidate_id,
            exam_session_id,
            event_type
        )

        # ----------------------------------------------------
        # COMMIT
        # ----------------------------------------------------

        connection.commit()

    except Exception as e:

        if connection:

            connection.rollback()

        print(
            "Browser event error:",
            e
        )

        return jsonify({
            "success": False,
            "message": "Could not save browser event"
        }), 500

    finally:

        if connection:

            connection.close()

    return jsonify({
        "success": True,
        "message": "Browser event saved"
    })


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():

    # Remove all session information.

    session.clear()

    return redirect(
        url_for("login")
    )


# ============================================================
# RUN FLASK APPLICATION
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )