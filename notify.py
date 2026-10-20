"""Email notifications via Resend. Falls back to printing when Resend isn't configured."""

import os

import httpx

RESEND_URL = "https://api.resend.com/emails"


def notify(subject: str, body: str) -> None:
    api_key, to = os.getenv("RESEND_API_KEY"), os.getenv("NOTIFY_EMAIL")
    if not api_key or not to:
        print(f"[notify] Email not configured, message was:\n{subject}\n\n{body}")
        return
    r = httpx.post(RESEND_URL, headers={"Authorization": f"Bearer {api_key}"}, json={
        # onboarding@resend.dev can only send to your own Resend account email;
        # verify a domain in Resend to send from your own address.
        "from": os.getenv("NOTIFY_FROM", "Weekly Tech Digest <onboarding@resend.dev>"),
        "to": [to],
        "subject": subject,
        "text": body,
    }, timeout=30)
    if r.status_code >= 400:
        print(f"[notify] Resend returned {r.status_code}: {r.text}")
