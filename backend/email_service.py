"""
email_service.py  (Gmail SMTP version)
---------------------------------------
Sends emails via Gmail SMTP — no third-party service needed.

Requirements in .env:
  SMTP_EMAIL      your Gmail address (e.g. you@gmail.com)
  SMTP_PASSWORD   Gmail App Password (16 chars, from myaccount.google.com)
  EMAIL_FROM      same as SMTP_EMAIL
  EMAIL_SUPPORT   support inbox (receives ticket emails)
  EMAIL_DEMO      sales inbox   (receives demo booking emails)
"""

import os
import smtplib
import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text      import MIMEText

SMTP_EMAIL    = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
EMAIL_FROM    = os.getenv("EMAIL_FROM",    SMTP_EMAIL or "")
EMAIL_SUPPORT = os.getenv("EMAIL_SUPPORT", "support@yourcompany.com")
EMAIL_DEMO    = os.getenv("EMAIL_DEMO",    "sales@yourcompany.com")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _send(to: str, subject: str, html: str) -> bool:
    """Core send helper — opens one SMTP connection per call."""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"]    = EMAIL_FROM
        msg["To"]      = to
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.sendmail(EMAIL_FROM, to, msg.as_string())

        print(f"[email] Sent to {to} — {subject}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("[email] Auth failed — check SMTP_EMAIL and SMTP_PASSWORD in .env")
        return False
    except Exception as e:
        print(f"[email] SMTP error: {e}")
        return False


# ── Support ticket ────────────────────────────────────────────────────────────

def send_ticket_email(ticket_id: str, name: str, email: str, description: str) -> bool:
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    support_html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#a78bfa;margin:0">🎫 New Support Ticket</h2>
        <p style="color:#888;margin:6px 0 0;font-size:14px">{timestamp}</p>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151;width:130px">Ticket ID</td>
            <td style="padding:10px">
              <span style="background:#f3f0ff;color:#6d28d9;padding:3px 10px;
                border-radius:12px;font-family:monospace">{ticket_id}</span>
            </td>
          </tr>
          <tr style="background:#f9fafb">
            <td style="padding:10px;font-weight:600;color:#374151">Customer</td>
            <td style="padding:10px;color:#111">{name}</td>
          </tr>
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151">Email</td>
            <td style="padding:10px">
              <a href="mailto:{email}" style="color:#6d28d9">{email}</a>
            </td>
          </tr>
          <tr style="background:#f9fafb">
            <td style="padding:10px;font-weight:600;color:#374151;vertical-align:top">Issue</td>
            <td style="padding:10px;color:#111;line-height:1.6">{description}</td>
          </tr>
        </table>
        <div style="margin-top:20px;padding:14px;background:#fef3c7;
          border-radius:6px;font-size:13px;color:#92400e">
          ⚡ Please respond to <strong>{email}</strong> within 24 hours.
        </div>
      </div>
    </div>"""

    user_html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#a78bfa;margin:0">We received your request ✅</h2>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <p style="color:#374151">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;margin-top:12px;line-height:1.6">
          Thanks for reaching out! We've logged your support request and our team
          will get back to you within <strong>24 hours</strong>.
        </p>
        <div style="margin:20px 0;padding:14px;background:#f5f3ff;border-radius:6px">
          <p style="margin:0;font-size:13px;color:#6d28d9">
            Your ticket reference:
            <strong style="font-family:monospace">{ticket_id}</strong>
          </p>
        </div>
        <p style="color:#6b7280;font-size:13px">The support team</p>
      </div>
    </div>"""

    ok1 = _send(EMAIL_SUPPORT, f"[{ticket_id}] New Support Ticket from {name}", support_html)
    ok2 = _send(email, f"We received your support request [{ticket_id}]", user_html)
    return ok1 and ok2


# ── Demo booking ──────────────────────────────────────────────────────────────

def send_demo_email(name: str, email: str, slot: str) -> bool:

    sales_html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#0f4c75;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#3ECFCF;margin:0">📅 New Demo Booking</h2>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse">
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151;width:130px">Name</td>
            <td style="padding:10px;color:#111">{name}</td>
          </tr>
          <tr style="background:#f9fafb">
            <td style="padding:10px;font-weight:600;color:#374151">Email</td>
            <td style="padding:10px">
              <a href="mailto:{email}" style="color:#0369a1">{email}</a>
            </td>
          </tr>
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151">Slot</td>
            <td style="padding:10px;color:#111"><strong>{slot}</strong></td>
          </tr>
        </table>
        <div style="margin-top:20px;padding:14px;background:#e0f2fe;
          border-radius:6px;font-size:13px;color:#0369a1">
          📌 Send a calendar invite to <strong>{email}</strong> for the confirmed slot.
        </div>
      </div>
    </div>"""

    user_html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#0f4c75;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#3ECFCF;margin:0">Your demo is booked! 🎉</h2>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;padding:24px;border-radius:0 0 8px 8px">
        <p style="color:#374151">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;margin-top:12px;line-height:1.6">
          Your demo has been scheduled for <strong>{slot}</strong>.
          Our team will send you a calendar invite shortly with the meeting link.
        </p>
        <p style="color:#6b7280;font-size:13px;margin-top:20px">The sales team</p>
      </div>
    </div>"""

    ok1 = _send(EMAIL_DEMO, f"New Demo Request — {name}", sales_html)
    ok2 = _send(email, "Your demo is confirmed!", user_html)
    return ok1 and ok2