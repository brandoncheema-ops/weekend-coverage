"""
Weekend Coverage App
- Serves a form where staff enter doctor names for Saturday & Sunday
- Stores submissions in a simple JSON file
- Sends a weekly email every Monday at 8 AM with a link to the form
- 100% free â deploy on Render
"""

import os
import json
import smtplib
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, render_template, request, jsonify, redirect, url_for
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Config â set these as environment variables on Render
# ---------------------------------------------------------------------------
GMAIL_USER = os.environ.get("GMAIL_USER", "")        # your Gmail address
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")  # Gmail App Password
RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL", "avolsky@gmail.com")
HR_EMAIL = os.environ.get("HR_EMAIL", "brandoncheema@gmail.com")
APP_URL = os.environ.get("APP_URL", "http://localhost:5000")  # your Render URL

DATA_FILE = Path("data/submissions.json")
DATA_FILE.parent.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_submissions():
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return []


def save_submission(entry):
    data = load_submissions()
    data.append(entry)
    DATA_FILE.write_text(json.dumps(data, indent=2))


def get_last_saturday_sunday():
    """Calculate last Saturday and Sunday dates from today."""
    today = datetime.now()
    days_since_saturday = (today.weekday() + 2) % 7  # Saturday = 5
    if days_since_saturday == 0:
        days_since_saturday = 7
    last_saturday = today - timedelta(days=days_since_saturday)
    last_sunday = last_saturday + timedelta(days=1)
    return last_saturday, last_sunday


def get_next_saturday_sunday():
    """Calculate the NEXT upcoming Saturday and Sunday from today."""
    today = datetime.now()
    days_until_saturday = (5 - today.weekday()) % 7
    if days_until_saturday == 0:
        days_until_saturday = 7
    next_saturday = today + timedelta(days=days_until_saturday)
    next_sunday = next_saturday + timedelta(days=1)
    return next_saturday, next_sunday


def send_hr_log_email(new_entry):
    """Send the new entry + full history log to HR after each submission."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[HR EMAIL] Gmail credentials not set â skipping.")
        return

    all_submissions = load_submissions()

    # Build history table rows
    history_rows = ""
    for s in reversed(all_submissions):
        history_rows += f"""
        <tr>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{s.get('saturday_date', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{s.get('saturday_doctor', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{s.get('sunday_date', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee;">{s.get('sunday_doctor', '')}</td>
            <td style="padding: 8px; border-bottom: 1px solid #eee; color: #999; font-size: 12px;">{s.get('submitted_at', '')[:16]}</td>
        </tr>"""

    html_body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 700px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #2c3e50; margin-top: 0;">New Weekend Coverage Entry</h2>
            <div style="background: #e8f5e9; border-radius: 8px; padding: 16px; margin-bottom: 24px;">
                <p style="margin: 0; color: #2e7d32; font-weight: bold;">Just Submitted:</p>
                <p style="margin: 8px 0 0 0; color: #333;">
                    Saturday {new_entry['saturday_date']}: <strong>{new_entry['saturday_doctor']}</strong><br>
                    Sunday {new_entry['sunday_date']}: <strong>{new_entry['sunday_doctor']}</strong>
                </p>
            </div>
            <h3 style="color: #2c3e50;">Full Entry Log</h3>
            <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
                <thead>
                    <tr style="background: #ecf0f1;">
                        <th style="padding: 10px; text-align: left;">Sat Date</th>
                        <th style="padding: 10px; text-align: left;">Sat Doctor</th>
                        <th style="padding: 10px; text-align: left;">Sun Date</th>
                        <th style="padding: 10px; text-align: left;">Sun Doctor</th>
                        <th style="padding: 10px; text-align: left;">Submitted</th>
                    </tr>
                </thead>
                <tbody>
                    {history_rows}
                </tbody>
            </table>
            <p style="color: #999; font-size: 12px; margin-top: 20px;">Total entries: {len(all_submissions)}</p>
        </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Weekend Coverage Log â {new_entry['saturday_date']} & {new_entry['sunday_date']}"
    msg["From"] = GMAIL_USER
    msg["To"] = HR_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, HR_EMAIL, msg.as_string())
        print(f"[HR EMAIL] Sent entry log to {HR_EMAIL}")
    except Exception as e:
        print(f"[HR EMAIL] Failed to send: {e}")


def build_email_html(saturday_date, sunday_date):
    """Build the HTML email body with dates and a Submit button."""
    sat_str = saturday_date.strftime("%B %d, %Y")
    sun_str = sunday_date.strftime("%B %d, %Y")
    form_url = f"{APP_URL}/weekend-coverage?sat={saturday_date.strftime('%Y-%m-%d')}&sun={sunday_date.strftime('%Y-%m-%d')}"

    return f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 30px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
            <h2 style="color: #2c3e50; margin-top: 0;">Weekend Coverage Reminder</h2>
            <p style="color: #555; font-size: 16px;">
                Please submit the doctor names for weekend coverage:
            </p>
            <table style="width: 100%; margin: 20px 0; border-collapse: collapse;">
                <tr>
                    <td style="padding: 10px; background: #ecf0f1; border-radius: 6px; font-weight: bold; color: #2c3e50;">
                        Saturday
                    </td>
                    <td style="padding: 10px; background: #ecf0f1; border-radius: 6px; color: #555;">
                        {sat_str}
                    </td>
                </tr>
                <tr><td colspan="2" style="height: 8px;"></td></tr>
                <tr>
                    <td style="padding: 10px; background: #ecf0f1; border-radius: 6px; font-weight: bold; color: #2c3e50;">
                        Sunday
                    </td>
                    <td style="padding: 10px; background: #ecf0f1; border-radius: 6px; color: #555;">
                        {sun_str}
                    </td>
                </tr>
            </table>
            <div style="text-align: center; margin-top: 25px;">
                <a href="{form_url}"
                   style="display: inline-block; background-color: #27ae60; color: white;
                          padding: 14px 40px; text-decoration: none; border-radius: 8px;
                          font-size: 18px; font-weight: bold;">
                    Submit Coverage
                </a>
            </div>
            <p style="color: #999; font-size: 12px; margin-top: 25px; text-align: center;">
                This is an automated weekly reminder.
            </p>
        </div>
    </body>
    </html>
    """


def send_weekly_email():
    """Send the Monday morning email with weekend dates."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("[EMAIL] Gmail credentials not set â skipping email send.")
        return

    saturday, sunday = get_last_saturday_sunday()
    sat_str = saturday.strftime("%B %d, %Y")
    sun_str = sunday.strftime("%B %d, %Y")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Weekend Coverage â {sat_str} & {sun_str}"
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    html_body = build_email_html(saturday, sunday)
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
        print(f"[EMAIL] Sent weekly email to {RECIPIENT_EMAIL}")
    except Exception as e:
        print(f"[EMAIL] Failed to send: {e}")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    """Home page â shows recent submissions."""
    submissions = load_submissions()
    # Show most recent first
    submissions.reverse()
    return render_template("index.html", submissions=submissions)


@app.route("/weekend-coverage")
def weekend_coverage_form():
    """The form page â dropdown of all weekends for the year, upcoming pre-selected."""
    sat = request.args.get("sat", "")
    sun = request.args.get("sun", "")

    # Build list of all weekends for the current year
    today = datetime.now()
    year = today.year
    # Find the first Saturday of the year
    jan1 = datetime(year, 1, 1)
    first_sat = jan1 + timedelta(days=(5 - jan1.weekday()) % 7)
    weekends = []
    d = first_sat
    # Go through the entire year (and into early Jan of next year to cover Dec weekends)
    end_date = datetime(year + 1, 1, 7)
    while d < end_date:
        sat_str = d.strftime("%Y-%m-%d")
        sun_str = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        weekends.append({"sat": sat_str, "sun": sun_str})
        d += timedelta(days=7)

    # Auto-select: use query params if provided, otherwise pick the upcoming weekend
    if not sat or not sun:
        # Find the next upcoming Saturday (or today if today is Saturday)
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0 and today.weekday() != 5:
            days_until_saturday = 7
        upcoming_sat = today + timedelta(days=days_until_saturday)
        sat = upcoming_sat.strftime("%Y-%m-%d")
        sun = (upcoming_sat + timedelta(days=1)).strftime("%Y-%m-%d")

    return render_template("form.html", sat=sat, sun=sun, weekends=weekends)


@app.route("/submit-coverage", methods=["POST"])
def submit_coverage():
    """Handle form submission, email HR, then advance to next week."""
    entry = {
        "saturday_date": request.form.get("saturday_date", ""),
        "saturday_doctor": request.form.get("saturday_doctor", "").strip(),
        "sunday_date": request.form.get("sunday_date", ""),
        "sunday_doctor": request.form.get("sunday_doctor", "").strip(),
        "submitted_at": datetime.now().isoformat(),
    }
    save_submission(entry)

    # Send entry log to HR (in background thread so form responds instantly)
    threading.Thread(target=send_hr_log_email, args=(entry,), daemon=True).start()

    # Advance to next weekend (add 7 days to the dates just submitted)
    submitted_sat = datetime.strptime(entry["saturday_date"], "%Y-%m-%d")
    next_sat = submitted_sat + timedelta(days=7)
    next_sun = next_sat + timedelta(days=1)
    return redirect(url_for(
        "weekend_coverage_form",
        sat=next_sat.strftime("%Y-%m-%d"),
        sun=next_sun.strftime("%Y-%m-%d"),
        submitted="1"
    ))


@app.route("/entry-log")
def entry_log():
    """View all past submissions in a clean table."""
    submissions = load_submissions()
    submissions.reverse()  # Most recent first
    return render_template("entry_log.html", submissions=submissions)


@app.route("/success")
def success():
    return render_template("success.html")


@app.route("/send-test-email")
def send_test_email():
    """Manual trigger to test the email (visit this URL once to verify)."""
    send_weekly_email()
    return "Test email sent! Check the inbox."


# ---------------------------------------------------------------------------
# Scheduler â sends email every Monday at 8 AM Eastern
# ---------------------------------------------------------------------------

scheduler = BackgroundScheduler(timezone=pytz.timezone("US/Eastern"))
scheduler.add_job(
    send_weekly_email,
    CronTrigger(day_of_week="mon", hour=8, minute=0),
    id="weekly_email",
    replace_existing=True,
)
scheduler.start()

# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
