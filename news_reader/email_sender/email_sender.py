import smtplib
import ssl
import os
import toml as tomlib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from custom_functions import path_utils

def send_summary_email(html_file_path):
    # 1. Load secrets from the local TOML file
    secrets_path = path_utils.get_resource_path(".streamlit/secrets.toml")
    try:
        with open(secrets_path, "r") as f:
            secrets = tomlib.load(f)["secrets"]
            # Make sure these keys match what you put in the TOML/GitHub Secrets
            sender_email = secrets["GMAIL_USER"]
            app_password = secrets["GMAIL_APP_PASSWORD"]
    except Exception as e:
        print(f"Error loading email secrets: {e}")
        return

    # 2. Read the HTML content
    try:
        with open(html_file_path, 'r', encoding='utf-8') as f:
            html_content = f.read()
    except FileNotFoundError:
        print(f"HTML file not found at {html_file_path}, cannot send email.")
        return

    # 3. Create Email Object
    msg = MIMEMultipart("alternative")
    # Clean up filename for the subject line
    filename = os.path.basename(html_file_path)
    msg["Subject"] = f"Daily News Summary: {filename}"
    msg["From"] = sender_email
    msg["To"] = sender_email # Sending to yourself

    # 4. Attach HTML body (This makes it render like a webpage in Gmail)
    part = MIMEText(html_content, "html")
    msg.attach(part)

    # 5. Send via Gmail SMTP (SSL)
    context = ssl.create_default_context()
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, sender_email, msg.as_string())
        print(f"Successfully sent email to {sender_email}")
    except Exception as e:
        print(f"Failed to send email: {e}")