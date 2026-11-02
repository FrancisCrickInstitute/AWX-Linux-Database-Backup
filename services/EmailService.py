import os
import smtplib
from email.message import EmailMessage
import config_backup as config
from services import utils
from services.LoggerService import logger, LogLevel


def send_email(title: str, body: str, e_type="error"):
    background_color = utils.get_background_color(e_type)
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Backup {e_type} on {config.managed_volume_name}: {title}"
        msg["From"] = config.emailfrom
        msg["To"] = config.emailto

        msg.set_content("This email requires an HTML-compatible email client.")
        html = str(utils.get_template()
                   .replace("{{SERVER}}", config.managed_volume_name)
                   .replace("{{SUBJECT}}", title or "Something went wrong")
                   .replace("{{BODY}}", body.strip())
                   .replace("{{E_TYPE}}", e_type)
                   .replace("{{BACKGROUND_COLOR}}", background_color))

        msg.add_alternative(html, subtype="html")

        with smtplib.SMTP("smtp.thecrick.org") as smtp:
            smtp.send_message(msg)



    except Exception as e:
        logger.log(
            level=LogLevel.WARNING,
            text=f"An error occurred while sending email: {e}",
        )
