"""
Email notification service: SMTP dispatch, template formatting, retry handling,
and transparent Simulated Demo Mode when SMTP credentials are not configured.
"""

import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from config.settings import settings, logger
from database.schema import Alert, Incident


class EmailService:
    @classmethod
    def send_alert_notification(
        cls,
        alert: Alert,
        recipient_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Send an email alert for a triggered monitoring rule.
        If SMTP is unconfigured, executes in Simulated Demo Mode with full logging.
        """
        recipient = recipient_override or settings.ALERT_RECIPIENT_EMAIL
        subject = f"[{alert.severity.upper()} ALERT] {alert.title} - {settings.APP_NAME}"

        # HTML and Plain text email body
        plain_text = (
            f"BUSINESS PROCESS MONITORING ALERT\n"
            f"---------------------------------\n"
            f"Alert ID:       {alert.alert_code}\n"
            f"Severity:       {alert.severity}\n"
            f"Category:       {alert.category}\n"
            f"Related Entity: {alert.related_entity_type.upper()} ({alert.related_entity_id})\n"
            f"Detected At:    {alert.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.detected_at else 'N/A'}\n\n"
            f"Description:\n{alert.description}\n\n"
            f"Recommended Action:\n"
            f"Open the Business Process Monitor Dashboard to review, acknowledge, and assign this alert.\n"
            f"Dashboard URL: http://localhost:8501\n"
        )

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #1e293b; background-color: #f8fafc; margin: 0; padding: 20px; }}
                .card {{ background: #ffffff; border-radius: 8px; border: 1px solid #e2e8f0; max-width: 600px; margin: 0 auto; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
                .header {{ background-color: {'#dc2626' if alert.severity == 'Critical' else '#ea580c' if alert.severity == 'High' else '#2563eb'}; color: white; padding: 18px 24px; }}
                .header h2 {{ margin: 0; font-size: 18px; font-weight: 600; }}
                .content {{ padding: 24px; }}
                .field {{ margin-bottom: 12px; }}
                .label {{ font-size: 12px; font-weight: 600; text-transform: uppercase; color: #64748b; margin-bottom: 2px; }}
                .value {{ font-size: 15px; color: #0f172a; }}
                .desc-box {{ background: #f1f5f9; padding: 14px; border-radius: 6px; border-left: 4px solid #94a3b8; font-size: 14px; line-height: 1.5; margin: 16px 0; }}
                .action-btn {{ display: inline-block; background-color: #0f172a; color: white; text-decoration: none; padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 500; margin-top: 10px; }}
                .footer {{ background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 14px 24px; font-size: 12px; color: #94a3b8; text-align: center; }}
            </style>
        </head>
        <body>
            <div class="card">
                <div class="header">
                    <h2>[{alert.severity.upper()}] {alert.title}</h2>
                </div>
                <div class="content">
                    <div class="field">
                        <div class="label">Alert Identifier</div>
                        <div class="value"><code>{alert.alert_code}</code></div>
                    </div>
                    <div class="field">
                        <div class="label">Category & Entity</div>
                        <div class="value">{alert.category} &bull; {alert.related_entity_type.capitalize()} <strong>{alert.related_entity_id}</strong></div>
                    </div>
                    <div class="field">
                        <div class="label">Detection Timestamp</div>
                        <div class="value">{alert.detected_at.strftime('%Y-%m-%d %H:%M:%S UTC') if alert.detected_at else 'N/A'}</div>
                    </div>
                    <div class="desc-box">
                        {alert.description}
                    </div>
                    <div class="field">
                        <div class="label">Recommended Action</div>
                        <div class="value">Log in to the operational command center to inspect records, acknowledge, and assign resolution owner.</div>
                    </div>
                    <a href="http://localhost:8501" class="action-btn">Open Dashboard &rarr;</a>
                </div>
                <div class="footer">
                    Sent automatically by {settings.APP_NAME} &bull; Operational Process Monitoring
                </div>
            </div>
        </body>
        </html>
        """

        # Check SMTP configuration
        if not settings.is_smtp_configured or not settings.ENABLE_EMAIL_ALERTS:
            # Simulated Demo Mode
            logger.info(
                f"[SIMULATED EMAIL DISPATCH] Alert {alert.alert_code} | "
                f"To: {recipient} | Subject: {subject} | "
                f"(Mode: Simulated Demo - SMTP credentials not set or ENABLE_EMAIL_ALERTS=False)"
            )
            return {
                "success": False,
                "delivered": False,
                "mode": "simulated_demo",
                "recipient": recipient,
                "subject": subject,
                "message": "Not sent. Notification was recorded in Simulated Demo Mode; configure SMTP to deliver it.",
            }

        # Real SMTP Delivery with retry handling
        return cls._dispatch_smtp(
            recipient=recipient,
            subject=subject,
            plain_text=plain_text,
            html_content=html_content,
        )

    @classmethod
    def test_smtp_connection(cls, test_recipient: Optional[str] = None) -> Dict[str, Any]:
        """Diagnostic function testing SMTP configuration and credentials."""
        if not settings.is_smtp_configured:
            return {
                "success": False,
                "mode": "simulated_demo",
                "error": "SMTP credentials not configured in settings or .env file (SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD required).",
            }

        recipient = test_recipient or settings.ALERT_RECIPIENT_EMAIL
        subject = f"[TEST] SMTP Diagnostic Verification - {settings.APP_NAME}"
        plain_text = "This is a diagnostic verification email sent by the Intelligent Business Process Monitoring System."
        html_content = "<p>This is a diagnostic verification email sent by <strong>Intelligent Business Process Monitoring System</strong>.</p>"

        return cls._dispatch_smtp(recipient, subject, plain_text, html_content)

    @classmethod
    def _dispatch_smtp(
        cls,
        recipient: str,
        subject: str,
        plain_text: str,
        html_content: str,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """Internal SMTP sender with TLS authentication and retry loop."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.SMTP_FROM_EMAIL
        msg["To"] = recipient

        msg.attach(MIMEText(plain_text, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"Connecting to SMTP server {settings.SMTP_HOST}:{settings.SMTP_PORT} (Attempt {attempt}/{max_retries})...")
                server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15)
                server.starttls()
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
                server.send_message(msg)
                server.quit()
                logger.info(f"Email successfully delivered to {recipient}")
                return {
                    "success": True,
                    "mode": "live_smtp",
                    "recipient": recipient,
                    "subject": subject,
                    "message": f"Email successfully delivered to {recipient}.",
                }
            except Exception as e:
                last_error = str(e)
                logger.warning(f"SMTP dispatch attempt {attempt} failed: {e}")
                if attempt < max_retries:
                    time.sleep(2)

        logger.error(f"Failed to dispatch email to {recipient} after {max_retries} attempts. Last error: {last_error}")
        return {
            "success": False,
            "mode": "live_smtp",
            "error": f"SMTP delivery failed: {last_error}",
        }
