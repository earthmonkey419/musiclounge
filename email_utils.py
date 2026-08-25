"""
Share Mode email delivery. Uses the host's own SMTP relay (config.py),
same BYOK philosophy as the Plex token — never a third-party email
provider dependency. Plain smtplib, per the scope doc.
"""
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import config


def send_share_email(to_email, share_url, content_title, from_display_name):
    """Sends the share link. From address stays fixed/domain-verified
    (config.SMTP_FROM_ADDRESS) — only the display name is admin-
    editable per share, matching the scope doc's reasoning about why
    a fully arbitrary From address isn't offered."""
    display_name = from_display_name or config.SMTP_FROM_DISPLAY_NAME

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"{display_name} shared music with you: {content_title}"
    msg["From"] = f"{display_name} <{config.SMTP_FROM_ADDRESS}>"
    msg["To"] = to_email

    text_body = (
        f"{display_name} shared \"{content_title}\" with you on MusicLounge.\n\n"
        f"Listen here: {share_url}\n\n"
        f"This link expires automatically — no account or app needed."
    )
    html_body = f"""
    <div style="font-family: sans-serif; max-width: 480px;">
      <p>{display_name} shared <strong>{content_title}</strong> with you on MusicLounge.</p>
      <p><a href="{share_url}" style="display:inline-block; background:#FF9137; color:#29231F;
         padding:12px 20px; border-radius:8px; text-decoration:none; font-weight:bold;">
         Listen now</a></p>
      <p style="color:#888; font-size:12px;">This link expires automatically — no account or app needed.</p>
    </div>
    """

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=10) as server:
        if config.SMTP_USE_TLS:
            server.starttls()
        if config.SMTP_USERNAME:
            server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        server.send_message(msg)
