# Student Portal

Flask app with guest login, exam schedule, results (SGPA/CGPA), calendar
(personal events + `.ics` export), attendance tracker and a study-plan
suggestions page. Demo data is generated in memory, so there is no database.

## Run locally

    pip install -r requirements.txt
    python app.py            # http://localhost:8000

Click **Continue as Guest** (or sign in with `guest` / `guest`).

## Docker

    docker build -t student-portal .
    docker run -p 8000:8000 -e SECRET_KEY="$(openssl rand -hex 32)" -e COOKIE_SECURE=0 student-portal

## Environment variables

| Variable          | Purpose                                                        |
|-------------------|----------------------------------------------------------------|
| `SECRET_KEY`      | Signs session cookies. **Set this in production.**             |
| `COOKIE_SECURE`   | Set to `1` when served over HTTPS so cookies are HTTPS-only.   |
| `PORT`            | Port to listen on (default 8000; cloud platforms often set it).|
| `WEB_CONCURRENCY` | Number of gunicorn workers (default 2).                        |
