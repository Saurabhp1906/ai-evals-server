import os
import resend

resend.api_key = os.environ.get("RESEND_API_KEY", "")

_FROM = os.environ.get("RESEND_FROM", "EvalPeak <noreply@yourdomain.com>")
_APP_URL = os.environ.get("APP_URL", "http://localhost:5173")


def send_invite_email(to_email: str, org_name: str, token: str) -> None:
    if not resend.api_key:
        return

    invite_url = f"{_APP_URL}/invite/{token}"

    resend.Emails.send({
        "from": _FROM,
        "to": [to_email],
        "subject": f"You're invited to join {org_name} on EvalPeak",
        "html": f"""
<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #f9fafb; margin: 0; padding: 40px 0;">
  <div style="max-width: 480px; margin: 0 auto; background: white; border-radius: 8px; border: 1px solid #e5e7eb; overflow: hidden;">
    <div style="background: #111827; padding: 24px 32px;">
      <h1 style="margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.3px;">
        <span style="color: white;">Eval</span><span style="color: #f97316;">Peak</span>
      </h1>
    </div>
    <div style="padding: 32px;">
      <h2 style="margin: 0 0 8px; font-size: 18px; color: #111827; font-weight: 600;">You're invited</h2>
      <p style="margin: 0 0 24px; color: #6b7280; font-size: 14px; line-height: 1.6;">
        You've been invited to join <strong style="color: #111827;">{org_name}</strong> on EvalPeak.
        Click the button below to accept.
      </p>
      <a href="{invite_url}"
         style="display: inline-block; background: #111827; color: white; text-decoration: none;
                padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 500;">
        Accept invitation
      </a>
      <p style="margin: 24px 0 0; color: #9ca3af; font-size: 12px;">
        This invite expires in 7 days. If you weren't expecting this, you can ignore this email.
      </p>
      <p style="margin: 8px 0 0; color: #9ca3af; font-size: 12px;">
        Or copy this link: <a href="{invite_url}" style="color: #6b7280;">{invite_url}</a>
      </p>
    </div>
  </div>
</body>
</html>
""",
    })
