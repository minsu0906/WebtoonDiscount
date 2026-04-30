from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Any


def build_email_subject(discounts: list[dict[str, Any]]) -> str:
    if len(discounts) == 1:
        return f"[레진 할인 알림] {discounts[0]['title']}"
    return f"[레진 할인 알림] 신규 할인 {len(discounts)}건"


def build_email_body(
    discounts: list[dict[str, Any]], errors: list[dict[str, str]]
) -> str:
    lines = ["새로운 레진코믹스 할인 알림입니다.", ""]

    for item in discounts:
        discount = item["discount"] or {}
        lines.append(f"작품: {item['title']}")
        lines.append(f"URL: {item['url']}")
        lines.append(
            "할인가: "
            + (
                f"{discount['discounted_price']}코인"
                if discount.get("discounted_price") is not None
                else "페이지에서 확인 불가"
            )
        )
        lines.append(
            "정가: "
            + (
                f"{discount['original_price']}코인"
                if discount.get("original_price") is not None
                else "페이지에서 확인 불가"
            )
        )
        lines.append(
            "할인율: "
            + (
                f"{discount['discount_rate']}%"
                if discount.get("discount_rate") is not None
                else "페이지에서 확인 불가"
            )
        )
        lines.append("기간: " + (discount.get("period_text") or "페이지에서 확인 불가"))
        lines.append("배너: " + (discount.get("banner_text") or "페이지에서 확인 불가"))
        lines.append("")

    if errors:
        lines.append("확인 중 오류가 발생한 작품")
        for error in errors:
            lines.append(f"- {error['target']}: {error['error']}")

    return "\n".join(lines).strip()


def send_email(
    smtp_host: str,
    smtp_port: int,
    sender_email: str,
    app_password: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> None:
    if not recipients:
        raise ValueError("At least one recipient email address is required.")

    message = MIMEText(body, _charset="utf-8")
    message["Subject"] = subject
    message["From"] = sender_email
    message["To"] = ", ".join(recipients)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(sender_email, app_password)
        server.sendmail(sender_email, recipients, message.as_string())
