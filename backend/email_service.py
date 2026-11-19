"""Email Notification Service for AccessGuard.

Supports real automated email delivery via Gmail SMTP (using Google App Passwords)
or standard TLS SMTP servers, plus audit logging of all dispatched alerts.
"""
from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import AdminEmailNotificationSetting, EmailAlertLog, now_utc

logger = logging.getLogger('email_service')


def get_or_create_email_settings(db: Session) -> AdminEmailNotificationSetting:
    """Retrieve existing admin email settings or initialize defaults."""
    setting = db.scalar(select(AdminEmailNotificationSetting).limit(1))
    if not setting:
        setting = AdminEmailNotificationSetting(
            admin_name='Security Administrator',
            admin_email='admin@security.example',
            enabled=1,
            smtp_host='smtp.gmail.com',
            smtp_port=587,
            smtp_user='',
            smtp_password='',
            sender_name='AccessGuard Security Sentinel',
            notify_on_high_risk=1,
            notify_on_attack_detected=1,
            notify_on_reviews_queued=1,
            updated_at=now_utc(),
        )
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def send_security_alert_email(
    db: Session,
    subject: str,
    html_content: str,
    text_content: str,
    trigger_type: str = 'attack_detection',
    recipient_override: Optional[str] = None
) -> dict[str, Any]:
    """Dispatch an automated security alert email using configured SMTP settings."""
    setting = get_or_create_email_settings(db)

    recipient = recipient_override or setting.admin_email
    if not recipient:
        return {'ok': False, 'status': 'skipped', 'message': 'No admin email configured.'}

    if not setting.enabled and not recipient_override:
        return {'ok': False, 'status': 'disabled', 'message': 'Email notifications are disabled.'}

    # Format email message
    msg = MIMEMultipart('alternative')
    sender_addr = setting.smtp_user if (setting.smtp_user and '@' in setting.smtp_user) else 'alerts@accessguard.local'
    msg['From'] = f"{setting.sender_name} <{sender_addr}>"
    msg['To'] = recipient
    msg['Subject'] = subject

    msg.attach(MIMEText(text_content, 'plain'))
    msg.attach(MIMEText(html_content, 'html'))

    # Check if SMTP credentials are provided for real sending
    is_real_smtp = bool(setting.smtp_host and setting.smtp_user and setting.smtp_password)
    status = 'simulated'
    error_msg = None

    if is_real_smtp:
        try:
            logger.info(f"Connecting to SMTP {setting.smtp_host}:{setting.smtp_port} for {recipient}...")
            if setting.smtp_port == 465:
                server = smtplib.SMTP_SSL(setting.smtp_host, setting.smtp_port, timeout=12)
            else:
                server = smtplib.SMTP(setting.smtp_host, setting.smtp_port, timeout=12)
                server.starttls()
            
            server.login(setting.smtp_user, setting.smtp_password)
            server.sendmail(sender_addr, [recipient], msg.as_string())
            server.quit()
            status = 'sent'
            logger.info(f"Real security alert email successfully sent to {recipient}")
        except Exception as ex:
            logger.error(f"Failed to send email via SMTP: {ex}")
            status = 'failed'
            error_msg = str(ex)
    else:
        # Logged as mock / simulated dispatch
        status = 'simulated'
        logger.info(f"Simulated email alert dispatched to {recipient}: {subject}")

    # Log to audit history
    log_entry = EmailAlertLog(
        recipient=recipient,
        subject=subject,
        body=text_content[:2000],
        status=status,
        error_message=error_msg,
        trigger_type=trigger_type,
        sent_at=now_utc(),
    )
    db.add(log_entry)
    db.commit()

    return {
        'ok': status in ('sent', 'simulated'),
        'status': status,
        'recipient': recipient,
        'subject': subject,
        'error': error_msg,
        'is_real_delivery': is_real_smtp and status == 'sent',
    }


def build_attack_alert_email_template(
    employee_name: str,
    department: str,
    risk_score: int,
    platform: str,
    detection_rule: str,
    scenario_name: str,
    dashboard_url: str = "http://127.0.0.1:5173"
) -> tuple[str, str, str]:
    """Construct professional security advisory email HTML and plain text."""
    subject = f"🚨 [CRITICAL ALERT] Malicious Role Breach Detected: {employee_name} ({platform.upper()})"

    text_body = f"""AccessGuard Security Alert Sentinel
===================================================
A high-severity unauthorized access progression or role breach was detected.

Target Identity: {employee_name}
Department: {department}
Target Platform: {platform.upper()}
Calculated Risk Score: {risk_score} / 100 (HIGH RISK)
Detection Rule: {detection_rule}
Triggering Scenario: {scenario_name}

Immediate Action Required:
1. Log in to AccessGuard Console ({dashboard_url})
2. Navigate to Access Reviews / Simulated Reviews
3. Review the pending revocation request and execute immediate remediation.

This is an automated security advisory.
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f7f6fb; margin: 0; padding: 24px; color: #28263d; }}
    .container {{ max-width: 620px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e5e0f0; overflow: hidden; box-shadow: 0 4px 16px rgba(0,0,0,0.06); }}
    .header {{ background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%); color: #ffffff; padding: 24px; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; display: flex; align-items: center; gap: 8px; }}
    .header p {{ margin: 6px 0 0; opacity: 0.9; font-size: 13px; }}
    .content {{ padding: 24px; line-height: 1.5; }}
    .alert-banner {{ background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px; margin-bottom: 20px; color: #991b1b; font-size: 14px; font-weight: 600; }}
    .details-table {{ width: 100%; border-collapse: collapse; margin-bottom: 24px; }}
    .details-table td {{ padding: 10px 12px; border-bottom: 1px solid #f1edf7; font-size: 13px; }}
    .details-table td.label {{ font-weight: 600; color: #585174; width: 38%; }}
    .details-table td.value {{ font-weight: 700; color: #1e1b2e; }}
    .score-badge {{ background: #fee2e2; color: #dc2626; padding: 4px 10px; border-radius: 6px; font-weight: 800; font-size: 14px; display: inline-block; }}
    .action-btn {{ display: inline-block; background: #6366f1; color: #ffffff !important; text-decoration: none; font-weight: 700; padding: 12px 24px; border-radius: 8px; font-size: 14px; text-align: center; }}
    .footer {{ background: #faf9fd; padding: 16px 24px; font-size: 12px; color: #7f7993; border-top: 1px solid #f1edf7; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>🚨 AccessGuard Security Sentinel</h1>
      <p>Automated High-Risk Privilege Anomaly & Role Breach Alert</p>
    </div>
    <div class="content">
      <div class="alert-banner">
        ⚠️ Immediate Human-in-the-Loop review required for identity <b>{employee_name}</b>.
      </div>

      <table class="details-table">
        <tr>
          <td class="label">Target Identity</td>
          <td class="value">{employee_name}</td>
        </tr>
        <tr>
          <td class="label">Department</td>
          <td class="value">{department}</td>
        </tr>
        <tr>
          <td class="label">Affected Platform</td>
          <td class="value">{platform.upper()}</td>
        </tr>
        <tr>
          <td class="label">Security Risk Score</td>
          <td class="value"><span class="score-badge">{risk_score} / 100 (HIGH RISK)</span></td>
        </tr>
        <tr>
          <td class="label">Detection Rule</td>
          <td class="value">{detection_rule}</td>
        </tr>
        <tr>
          <td class="label">Triggered Incident</td>
          <td class="value">{scenario_name}</td>
        </tr>
      </table>

      <div style="text-align: center; margin: 28px 0 16px;">
        <a href="{dashboard_url}" class="action-btn">Open Access Reviews & Remediate →</a>
      </div>
    </div>
    <div class="footer">
      Sent automatically by AccessGuard Autonomous Defense Engine • Destination: Main Administrator
    </div>
  </div>
</body>
</html>
"""
    return subject, html_body, text_body
