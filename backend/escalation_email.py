"""
escalation_email.py
-------------------
Sends escalation notification emails via Gmail SMTP.

Two emails per escalation:
  1. Support team  — full context: user info, reason, conversation transcript
  2. User          — reassurance that a human will follow up

Env vars (same as email_service.py):
  SMTP_EMAIL, SMTP_PASSWORD, EMAIL_FROM, EMAIL_SUPPORT
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

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Human-readable reason labels
REASON_LABELS = {
    "explicit":       "User requested a human agent",
    "frustrated":     "User appears frustrated or upset",
    "sensitive":      "Sensitive topic detected (legal / billing / privacy)",
    "low_confidence": "Bot confidence too low to answer reliably",
}


def _send(to: str, subject: str, html: str) -> bool:
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

        print(f"[escalation] Email sent to {to}")
        return True
    except Exception as e:
        print(f"[escalation] Email error: {e}")
        return False


def _transcript_html(history: list[dict]) -> str:
    """Format last 10 turns of conversation as HTML table rows."""
    rows = ""
    for msg in history[-10:]:
        role  = msg["role"].capitalize()
        color = "#374151" if role == "User" else "#6d28d9"
        rows += f"""
        <tr>
          <td style="padding:8px 12px;font-weight:600;color:{color};
            white-space:nowrap;vertical-align:top;width:90px">{role}</td>
          <td style="padding:8px 12px;color:#374151;line-height:1.6">
            {msg['content']}
          </td>
        </tr>"""
    return rows


def send_escalation_email(
    name: str,
    email: str,
    reason: str,
    last_message: str,
    history: list[dict],
    escalation_id: str,
) -> bool:
    timestamp    = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    reason_label = REASON_LABELS.get(reason, reason)
    transcript   = _transcript_html(history)

    # ── Email to support team ─────────────────────────────────────────────────
    support_html = f"""
    <div style="font-family:sans-serif;max-width:680px;margin:0 auto">
      <div style="background:#7c1d1d;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#fca5a5;margin:0">🚨 Escalation — Human Handoff Required</h2>
        <p style="color:#fecaca;margin:6px 0 0;font-size:14px">{timestamp}</p>
      </div>

      <div style="border:1px solid #e5e7eb;border-top:none;
        padding:24px;border-radius:0 0 8px 8px">

        <!-- Meta -->
        <table style="width:100%;border-collapse:collapse;margin-bottom:20px">
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151;width:150px">Escalation ID</td>
            <td style="padding:10px">
              <span style="background:#fef2f2;color:#b91c1c;padding:3px 10px;
                border-radius:12px;font-family:monospace">{escalation_id}</span>
            </td>
          </tr>
          <tr style="background:#f9fafb">
            <td style="padding:10px;font-weight:600;color:#374151">Customer</td>
            <td style="padding:10px;color:#111">{name}</td>
          </tr>
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151">Email</td>
            <td style="padding:10px">
              <a href="mailto:{email}" style="color:#b91c1c">{email}</a>
            </td>
          </tr>
          <tr style="background:#f9fafb">
            <td style="padding:10px;font-weight:600;color:#374151">Reason</td>
            <td style="padding:10px;color:#111">{reason_label}</td>
          </tr>
          <tr>
            <td style="padding:10px;font-weight:600;color:#374151;vertical-align:top">
              Last message
            </td>
            <td style="padding:10px;color:#111;line-height:1.6;font-style:italic">
              "{last_message}"
            </td>
          </tr>
        </table>

        <!-- Transcript -->
        <h3 style="font-size:14px;color:#374151;margin-bottom:8px">
          Conversation transcript (last 10 turns)
        </h3>
        <table style="width:100%;border-collapse:collapse;
          border:1px solid #e5e7eb;border-radius:6px;overflow:hidden">
          {transcript}
        </table>

        <!-- CTA -->
        <div style="margin-top:20px;padding:14px;background:#fef2f2;
          border-radius:6px;font-size:13px;color:#b91c1c">
          ⚡ Please reach out to <strong>{email}</strong> as soon as possible.
          Reference escalation ID <strong>{escalation_id}</strong> in your reply.
        </div>
      </div>
    </div>"""

    # ── Email to user ─────────────────────────────────────────────────────────
    user_html = f"""
    <div style="font-family:sans-serif;max-width:600px;margin:0 auto">
      <div style="background:#1a1a2e;padding:24px;border-radius:8px 8px 0 0">
        <h2 style="color:#a78bfa;margin:0">You're connected with our team 🤝</h2>
      </div>
      <div style="border:1px solid #e5e7eb;border-top:none;
        padding:24px;border-radius:0 0 8px 8px">
        <p style="color:#374151">Hi <strong>{name}</strong>,</p>
        <p style="color:#374151;margin-top:12px;line-height:1.6">
          We've flagged your conversation and a member of our support team
          will reach out to you at <strong>{email}</strong> shortly —
          usually within a few hours during business hours.
        </p>
        <div style="margin:20px 0;padding:14px;background:#f5f3ff;border-radius:6px">
          <p style="margin:0;font-size:13px;color:#6d28d9">
            Reference ID: <strong style="font-family:monospace">{escalation_id}</strong>
          </p>
        </div>
        <p style="color:#374151;line-height:1.6">
          If it's urgent, you can also email us directly at
          <a href="mailto:{EMAIL_SUPPORT}" style="color:#6d28d9">{EMAIL_SUPPORT}</a>.
        </p>
        <p style="color:#6b7280;font-size:13px;margin-top:20px">The support team</p>
      </div>
    </div>"""

    ok1 = _send(
        EMAIL_SUPPORT,
        f"🚨 [{escalation_id}] Escalation — {reason_label}",
        support_html,
    )
    ok2 = _send(
        email,
        "Our team will be in touch shortly",
        user_html,
    )
    return ok1 and ok2
