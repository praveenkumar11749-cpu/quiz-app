"""Student Portal - a small Flask application.

Features: guest login, exam schedule, results (SGPA/CGPA), calendar with
personal events + .ics export, attendance tracker and a study-plan
"suggestions" page.  All demo data is generated in memory relative to
today's date, so the app always looks current and needs no database.
"""
import calendar
import hashlib
import hmac
import math
import os
import secrets
from datetime import date, datetime, timedelta, timezone
from functools import wraps

from flask import (Flask, Response, abort, flash, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)

_secret = os.environ.get("SECRET_KEY")
if not _secret:
    _secret = secrets.token_hex(32)
    app.logger.warning(
        "SECRET_KEY is not set - using a random key. Sessions will reset on "
        "restart and will not be shared between instances. Set SECRET_KEY in "
        "production."
    )

app.config.update(
    SECRET_KEY=_secret,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Set COOKIE_SECURE=1 when serving over HTTPS (most cloud platforms do).
    SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
    PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    MAX_CONTENT_LENGTH=64 * 1024,
)

# --------------------------------------------------------------------------
# Users (guest only for now - add more entries to enable real accounts)
# --------------------------------------------------------------------------
USERS = {
    "guest": {
        "password_hash": generate_password_hash("guest"),
        "name": "Guest Student",
        "roll_no": "GUEST-0001",
        "program": "B.Tech - Computer Science & Engineering",
        "semester": 5,
        "section": "A",
        "email": "guest@student.example.edu",
    }
}

NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("exams", "Exams"),
    ("results", "Results"),
    ("calendar_view", "Calendar"),
    ("attendance", "Attendance"),
    ("suggestions", "Suggestions"),
]

# --------------------------------------------------------------------------
# Demo data
# --------------------------------------------------------------------------
# Current semester (5): mid-term marks out of 30 and attendance so far.
COURSES = [
    {"code": "CS501", "name": "Operating Systems", "credits": 4,
     "mid": 21, "mid_max": 30, "attended": 38, "held": 42},
    {"code": "CS502", "name": "Database Management Systems", "credits": 4,
     "mid": 25, "mid_max": 30, "attended": 35, "held": 40},
    {"code": "CS503", "name": "Computer Networks", "credits": 3,
     "mid": 16, "mid_max": 30, "attended": 28, "held": 40},
    {"code": "CS504", "name": "Theory of Computation", "credits": 3,
     "mid": 14, "mid_max": 30, "attended": 30, "held": 41},
    {"code": "CS505", "name": "Software Engineering", "credits": 3,
     "mid": 24, "mid_max": 30, "attended": 33, "held": 36},
    {"code": "HS501", "name": "Professional Ethics", "credits": 2,
     "mid": 22, "mid_max": 30, "attended": 20, "held": 22},
]
COURSE_BY_CODE = {c["code"]: c for c in COURSES}

# (day offset from today, course code, kind, start time, minutes, room)
EXAM_PLAN = [
    (-40, "CS501", "Mid-Term", "10:00", 90, "Hall A-101"),
    (-39, "CS502", "Mid-Term", "10:00", 90, "Hall A-102"),
    (-38, "CS503", "Mid-Term", "10:00", 90, "Hall A-101"),
    (-37, "CS504", "Mid-Term", "10:00", 90, "Hall A-103"),
    (-36, "CS505", "Mid-Term", "10:00", 90, "Hall A-102"),
    (-35, "HS501", "Mid-Term", "10:00", 60, "Hall A-101"),
    (4, "CS503", "End-Term", "10:00", 180, "Hall B-204"),
    (7, "CS501", "End-Term", "10:00", 180, "Hall B-201"),
    (10, "CS504", "End-Term", "14:00", 180, "Hall B-203"),
    (13, "CS502", "End-Term", "10:00", 180, "Hall B-201"),
    (16, "CS505", "End-Term", "10:00", 180, "Hall B-202"),
    (18, "HS501", "End-Term", "10:00", 120, "Hall B-204"),
]

# Past semesters: (code, title, credits, marks out of 100)
PAST_SEMESTERS = [
    {"number": 1, "published": "Jan 2025", "courses": [
        ("MA101", "Engineering Mathematics I", 4, 86),
        ("PH101", "Engineering Physics", 4, 78),
        ("CS101", "Programming in C", 4, 91),
        ("EE101", "Basic Electrical Engineering", 3, 72),
        ("HS101", "Communication Skills", 2, 84),
        ("ME101", "Engineering Graphics", 3, 69)]},
    {"number": 2, "published": "Jun 2025", "courses": [
        ("MA102", "Engineering Mathematics II", 4, 81),
        ("CH101", "Engineering Chemistry", 4, 74),
        ("CS102", "Data Structures", 4, 93),
        ("EC101", "Basic Electronics", 3, 77),
        ("CS103", "Discrete Mathematics", 3, 88),
        ("HS102", "Environmental Science", 2, 90)]},
    {"number": 3, "published": "Jan 2026", "courses": [
        ("CS201", "Object Oriented Programming", 4, 89),
        ("CS202", "Digital Logic Design", 3, 76),
        ("CS203", "Design & Analysis of Algorithms", 4, 84),
        ("MA201", "Probability & Statistics", 3, 71),
        ("CS204", "Computer Organization", 3, 79),
        ("HS201", "Economics for Engineers", 2, 82)]},
    {"number": 4, "published": "Jun 2026", "courses": [
        ("CS205", "Microprocessors", 3, 73),
        ("CS206", "Java Programming", 4, 92),
        ("CS207", "Compiler Fundamentals", 3, 68),
        ("CS208", "Web Technologies", 3, 90),
        ("MA202", "Numerical Methods", 3, 75),
        ("CS209", "Data Structures Lab", 2, 95)]},
]

GRADE_SCALE = [(90, "O", 10), (80, "A+", 9), (70, "A", 8),
               (60, "B+", 7), (50, "B", 6), (40, "C", 5), (0, "F", 0)]

FIXED_HOLIDAYS = [
    (1, 1, "New Year's Day"),
    (1, 26, "Republic Day"),
    (8, 15, "Independence Day"),
    (10, 2, "Gandhi Jayanti"),
    (12, 25, "Christmas Day"),
]

ROADMAP = [
    ("Real accounts", "Replace the guest user with college SSO or a database "
                      "table of students with hashed passwords."),
    ("Hall ticket download", "Generate a PDF hall ticket once exam fees and "
                             "attendance eligibility are confirmed."),
    ("Push / email reminders", "Notify students 3 days, 1 day and 2 hours "
                               "before every exam."),
    ("Fee payments", "Show dues and receipts and link to the payment gateway."),
    ("Timetable & room finder", "Weekly class timetable with room map and "
                                "faculty contact."),
    ("Revaluation requests", "Let students apply for re-evaluation from the "
                             "results page and track the status."),
    ("Study groups", "Match students who share upcoming exams and want to "
                     "study together."),
    ("Admin console", "Let the exam cell publish schedules and results "
                      "without touching code."),
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def today_date():
    return date.today()


def grade_for(marks):
    for floor, letter, points in GRADE_SCALE:
        if marks >= floor:
            return letter, points
    return "F", 0


def _skip_sunday(d):
    return d + timedelta(days=1) if d.weekday() == 6 else d


def get_exams(today):
    exams = []
    for offset, code, kind, start, minutes, room in EXAM_PLAN:
        d = _skip_sunday(today + timedelta(days=offset))
        start_dt = datetime.combine(d, datetime.strptime(start, "%H:%M").time())
        end_dt = start_dt + timedelta(minutes=minutes)
        days_left = (d - today).days
        exams.append({
            "date": d,
            "code": code,
            "name": COURSE_BY_CODE[code]["name"],
            "kind": kind,
            "start": start_dt,
            "end": end_dt,
            "minutes": minutes,
            "room": room,
            "days_left": days_left,
            "status": ("completed" if days_left < 0
                       else "today" if days_left == 0 else "upcoming"),
        })
    exams.sort(key=lambda e: e["start"])
    return exams


def get_results():
    semesters = []
    total_points = 0.0
    total_credits = 0
    for sem in PAST_SEMESTERS:
        rows, sem_points, sem_credits = [], 0.0, 0
        for code, title, credits, marks in sem["courses"]:
            letter, points = grade_for(marks)
            rows.append({"code": code, "title": title, "credits": credits,
                         "marks": marks, "grade": letter, "points": points,
                         "passed": letter != "F"})
            sem_points += points * credits
            sem_credits += credits
        total_points += sem_points
        total_credits += sem_credits
        semesters.append({
            "number": sem["number"],
            "published": sem["published"],
            "rows": rows,
            "credits": sem_credits,
            "sgpa": round(sem_points / sem_credits, 2),
            "cgpa": round(total_points / total_credits, 2),
        })
    return {
        "semesters": semesters,
        "cgpa": round(total_points / total_credits, 2),
        "credits": total_credits,
    }


def attendance_summary():
    rows, attended_all, held_all = [], 0, 0
    for c in COURSES:
        a, t = c["attended"], c["held"]
        pct = round(100 * a / t, 1)
        rows.append({
            "code": c["code"],
            "name": c["name"],
            "attended": a,
            "held": t,
            "pct": pct,
            "status": "good" if pct >= 85 else "ok" if pct >= 75 else "low",
            # classes to attend in a row to get back to 75%
            "need": max(0, 3 * t - 4 * a),
            # classes that can still be missed while staying at 75%
            "can_skip": max(0, (4 * a - 3 * t) // 3),
        })
        attended_all += a
        held_all += t
    return {"rows": rows,
            "overall": round(100 * attended_all / held_all, 1)}


def get_announcements(today):
    return [
        {"date": today - timedelta(days=1), "title": "Hall tickets available",
         "body": "Download your End-Term hall ticket from the exam cell. "
                 "Carry it along with your college ID."},
        {"date": today - timedelta(days=3), "title": "End-Term schedule published",
         "body": "The final schedule is on the Exams page. Report 20 minutes "
                 "before the start time."},
        {"date": today - timedelta(days=6), "title": "Library open till 10 PM",
         "body": "The central library extends its hours during the exam "
                 "period."},
    ]


def _event_uid(kind, d, title):
    digest = hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]
    return f"{kind}-{d.isoformat()}-{digest}"


def get_events(today, years=None):
    """All calendar events (exams, deadlines, holidays, personal)."""
    years = years or {today.year - 1, today.year, today.year + 1}
    events = []

    for e in get_exams(today):
        title = f"{e['code']} {e['kind']} - {e['name']}"
        events.append({
            "date": e["date"], "title": title, "type": "exam",
            "time": e["start"].strftime("%H:%M"),
            "start": e["start"], "end": e["end"],
            "uid": _event_uid("exam", e["date"], title),
        })

    deadlines = [
        (2, "Operating Systems lab record due", "deadline"),
        (5, "Last date for exam fee payment", "deadline"),
        (9, "Project viva - Software Engineering", "event"),
        (15, "Internship report submission", "deadline"),
        (21, "Winter break begins", "holiday"),
    ]
    for offset, title, kind in deadlines:
        d = today + timedelta(days=offset)
        events.append({"date": d, "title": title, "type": kind, "time": "",
                       "start": None, "end": None,
                       "uid": _event_uid(kind, d, title)})

    for y in years:
        for month, day, title in FIXED_HOLIDAYS:
            d = date(y, month, day)
            events.append({"date": d, "title": title, "type": "holiday",
                           "time": "", "start": None, "end": None,
                           "uid": _event_uid("holiday", d, title)})

    for p in session.get("events", []):
        try:
            d = date.fromisoformat(p["date"])
        except (ValueError, KeyError, TypeError):
            continue
        events.append({"date": d, "title": p.get("title", ""), "type": "personal",
                       "time": "", "start": None, "end": None,
                       "id": p.get("id"),
                       "uid": _event_uid("personal", d, p.get("title", ""))})

    events.sort(key=lambda ev: (ev["date"], ev["time"]))
    return events


def study_plan(today):
    plan = []
    attendance = {r["code"]: r for r in attendance_summary()["rows"]}
    for e in get_exams(today):
        if e["kind"] != "End-Term" or e["days_left"] < 0:
            continue
        c = COURSE_BY_CODE[e["code"]]
        mid_pct = 100 * c["mid"] / c["mid_max"]
        hours = 1.0 + 0.25 * c["credits"]
        reasons = []
        if mid_pct < 60:
            hours += 1.0
            reasons.append(f"Mid-term score was {mid_pct:.0f}% - revise basics first")
        if e["days_left"] <= 3:
            hours += 0.5
            reasons.append("Exam is within 3 days - switch to past papers")
        if attendance[e["code"]]["status"] == "low":
            reasons.append("Attendance is below 75% - collect missed notes")
        hours = round(hours * 2) / 2
        days = max(e["days_left"], 1)
        priority = "High" if (mid_pct < 60 or e["days_left"] <= 3) else "Normal"
        plan.append({
            "code": e["code"], "name": e["name"], "date": e["date"],
            "days_left": e["days_left"], "hours_per_day": hours,
            "total_hours": hours * days, "priority": priority,
            "reasons": reasons or ["On track - keep a steady revision pace"],
        })
    return plan


def month_grid(year, month, events, today):
    by_date = {}
    for ev in events:
        by_date.setdefault(ev["date"], []).append(ev)
    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append([{
            "date": d,
            "in_month": d.month == month,
            "is_today": d == today,
            "events": by_date.get(d, []),
        } for d in week])
    return weeks


def _ics_escape(text):
    return (text.replace("\\", "\\\\").replace(";", "\\;")
                .replace(",", "\\,").replace("\n", "\\n"))


# --------------------------------------------------------------------------
# Auth, CSRF and security headers
# --------------------------------------------------------------------------
def current_user():
    username = session.get("user")
    user = USERS.get(username) if username else None
    return dict(user, username=username) if user else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapper


def _start_session(username):
    session.clear()
    session["user"] = username
    session["csrf"] = secrets.token_hex(16)
    session.permanent = True


@app.before_request
def csrf_protect():
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        expected = session.get("csrf", "")
        sent = request.form.get("csrf_token", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, "Your session expired or the form was invalid. "
                       "Please go back and try again.")


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
    return resp


@app.context_processor
def inject_globals():
    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_hex(16)
        return session["csrf"]
    return {"csrf_token": csrf_token, "user": current_user(),
            "today": today_date(), "nav_items": NAV_ITEMS}


@app.errorhandler(400)
@app.errorhandler(404)
@app.errorhandler(405)
@app.errorhandler(500)
def handle_error(err):
    code = getattr(err, "code", 500)
    message = getattr(err, "description", "Something went wrong.")
    return render_template("error.html", code=code, message=message), code


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/")
def index():
    return redirect(url_for("dashboard" if current_user() else "login"))


@app.get("/login")
def login():
    if current_user():
        return redirect(url_for("dashboard"))
    return render_template("login.html")


@app.post("/login")
def login_post():
    username = request.form.get("username", "").strip().lower()
    password = request.form.get("password", "")
    user = USERS.get(username)
    if user and check_password_hash(user["password_hash"], password):
        _start_session(username)
        return redirect(url_for("dashboard"))
    flash("Invalid username or password.", "error")
    return redirect(url_for("login"))


@app.post("/login/guest")
def login_guest():
    _start_session("guest")
    flash("You are browsing as a guest with demo data.", "info")
    return redirect(url_for("dashboard"))


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required
def dashboard():
    t = today_date()
    exams = [e for e in get_exams(t) if e["days_left"] >= 0]
    horizon = t + timedelta(days=14)
    upcoming_events = [ev for ev in get_events(t)
                       if t <= ev["date"] <= horizon][:6]
    return render_template(
        "dashboard.html",
        next_exam=exams[0] if exams else None,
        exams_left=len(exams),
        results=get_results(),
        attendance=attendance_summary(),
        upcoming_events=upcoming_events,
        announcements=get_announcements(t),
    )


@app.get("/exams")
@login_required
def exams():
    t = today_date()
    all_exams = get_exams(t)
    return render_template(
        "exams.html",
        upcoming=[e for e in all_exams if e["days_left"] >= 0],
        completed=[e for e in all_exams if e["days_left"] < 0][::-1],
    )


@app.get("/results")
@login_required
def results():
    return render_template("results.html", results=get_results(),
                           scale=GRADE_SCALE)


@app.get("/calendar")
@login_required
def calendar_view():
    t = today_date()
    try:
        year = int(request.args.get("year", t.year))
        month = int(request.args.get("month", t.month))
        if not (1 <= month <= 12 and 2000 <= year <= 2100):
            raise ValueError
    except ValueError:
        year, month = t.year, t.month

    first = date(year, month, 1)
    prev_month = first - timedelta(days=1)
    next_month = (first + timedelta(days=32)).replace(day=1)

    events = get_events(t, years={year - 1, year, year + 1})
    agenda = [ev for ev in events
              if t <= ev["date"] <= t + timedelta(days=30)][:10]
    return render_template(
        "calendar.html",
        weeks=month_grid(year, month, events, t),
        month_name=calendar.month_name[month],
        year=year, month=month,
        prev=prev_month, next=next_month,
        agenda=agenda,
        personal=[ev for ev in events if ev["type"] == "personal"],
        weekdays=list(calendar.day_abbr),
    )


@app.post("/calendar/add")
@login_required
def calendar_add():
    title = request.form.get("title", "").strip()[:60]
    raw_date = request.form.get("date", "")
    try:
        d = date.fromisoformat(raw_date)
    except ValueError:
        d = None
    personal = session.get("events", [])
    if not title or d is None:
        flash("Please enter a title and a valid date.", "error")
    elif len(personal) >= 20:
        flash("You can keep at most 20 personal events.", "error")
    else:
        personal.append({"id": secrets.token_hex(4), "date": d.isoformat(),
                         "title": title})
        session["events"] = personal
        flash("Event added to your calendar.", "info")
    target = d or today_date()
    return redirect(url_for("calendar_view", year=target.year,
                            month=target.month))


@app.post("/calendar/delete")
@login_required
def calendar_delete():
    event_id = request.form.get("id", "")
    session["events"] = [p for p in session.get("events", [])
                         if p.get("id") != event_id]
    flash("Event removed.", "info")
    return redirect(url_for("calendar_view"))


@app.get("/calendar.ics")
@login_required
def calendar_ics():
    t = today_date()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0",
             "PRODID:-//Student Portal//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Student Portal"]
    for ev in get_events(t, years={t.year, t.year + 1}):
        lines += ["BEGIN:VEVENT", f"UID:{ev['uid']}@student-portal",
                  f"DTSTAMP:{stamp}"]
        if ev["start"]:
            lines.append("DTSTART:" + ev["start"].strftime("%Y%m%dT%H%M%S"))
            lines.append("DTEND:" + ev["end"].strftime("%Y%m%dT%H%M%S"))
        else:
            lines.append("DTSTART;VALUE=DATE:" + ev["date"].strftime("%Y%m%d"))
            end = ev["date"] + timedelta(days=1)
            lines.append("DTEND;VALUE=DATE:" + end.strftime("%Y%m%d"))
        lines.append("SUMMARY:" + _ics_escape(ev["title"]))
        lines.append("CATEGORIES:" + ev["type"].upper())
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return Response(
        "\r\n".join(lines) + "\r\n", mimetype="text/calendar",
        headers={"Content-Disposition":
                 "attachment; filename=student-calendar.ics"})


@app.get("/attendance")
@login_required
def attendance():
    return render_template("attendance.html", attendance=attendance_summary())


@app.get("/suggestions")
@login_required
def suggestions():
    t = today_date()
    att = attendance_summary()
    return render_template(
        "suggestions.html",
        plan=study_plan(t),
        low_attendance=[r for r in att["rows"] if r["status"] == "low"],
        roadmap=ROADMAP,
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
