from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any

import requests

from checker import check_webtoon
from config import load_settings
from lezhin_auth import apply_lezhin_session
from notifier import (
    build_email_body,
    build_email_subject,
    chunk_receiver_uuids,
    get_kakao_access_token,
    resolve_kakao_friend_uuids,
    send_email,
    send_kakao_discount_alert,
)


logger = logging.getLogger(__name__)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_state(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"webtoons": {}, "meta": {}, "kakao": {}}

    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except json.JSONDecodeError:
        logger.warning("State file is not valid JSON. Recreating: %s", path)
        return {"webtoons": {}, "meta": {}, "kakao": {}}

    if not isinstance(data, dict):
        logger.warning("State file format is invalid. Recreating: %s", path)
        return {"webtoons": {}, "meta": {}, "kakao": {}}

    data.setdefault("webtoons", {})
    data.setdefault("meta", {})
    data.setdefault("kakao", {})
    return data


def save_state(path: str, state: dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def mark_discount_notified(
    state: dict[str, Any], item: dict[str, Any], notified_at: str
) -> None:
    state["meta"]["last_run_at"] = notified_at
    state_entry = state["webtoons"][item["identifier"]]
    state_entry["last_notified_discount_signature"] = state_entry[
        "current_discount_signature"
    ]
    state_entry["last_notification_at"] = notified_at


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check Lezhin discounts and send notifications."
    )
    parser.add_argument(
        "--test-notification",
        action="store_true",
        help="Send a sample notification with the current provider settings.",
    )
    return parser.parse_args()


def build_test_discount_item(settings: dict[str, Any]) -> dict[str, Any]:
    default_url = "https://www.lezhin.com"
    configured_url = next(
        (item.get("url") for item in settings["webtoons"] if item.get("url")),
        default_url,
    )

    return {
        "identifier": "__test_notification__",
        "title": "[테스트] 레진 할인 알림",
        "url": configured_url or default_url,
        "requested_title": "테스트 알림",
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "discount": {
            "banner_text": "[3 -> 1코인] 테스트 알림입니다. 실제 할인은 아닙니다.",
            "original_price": 3,
            "discounted_price": 1,
            "discount_rate": 66.67,
            "period_text": "오늘 23:59까지 (테스트용)",
            "deadline_iso": None,
            "signature": "__test_notification__",
        },
    }


def send_notifications(
    settings: dict[str, Any],
    state: dict[str, Any],
    discounts: list[dict[str, Any]],
    errors: list[dict[str, str]],
    *,
    mark_state: bool,
) -> bool:
    notification_failed = False

    if not discounts:
        logger.info("No discounts to notify.")
        return notification_failed

    provider = settings["notification_provider"]

    if provider == "email":
        try:
            send_email(
                smtp_host=settings["smtp_host"],
                smtp_port=settings["smtp_port"],
                sender_email=settings["email_sender"],
                app_password=settings["email_app_password"],
                recipients=settings["email_recipients"],
                subject=build_email_subject(discounts),
                body=build_email_body(discounts, errors),
            )
            if mark_state:
                notified_at = datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )
                for item in discounts:
                    mark_discount_notified(state, item, notified_at)
            logger.info(
                "Email notification sent for %d item(s)",
                len(discounts),
            )
        except Exception as error:
            logger.exception("Failed to send email notification: %s", error)
            notification_failed = True

        return notification_failed

    try:
        token_info = get_kakao_access_token(
            rest_api_key=settings["kakao_rest_api_key"],
            refresh_tokens=[
                state["kakao"].get("refresh_token"),
                settings["kakao_refresh_token"],
            ],
            client_secret=settings["kakao_client_secret"],
            timeout_seconds=settings["request_timeout_seconds"],
        )
        state["kakao"]["refresh_token"] = token_info["refresh_token"]
        state["kakao"]["last_token_refresh_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
    except Exception as error:
        logger.exception("Failed to prepare KakaoTalk notification: %s", error)
        return True

    receiver_chunks: list[list[str] | None]
    if provider == "kakao_friends":
        try:
            receiver_uuids = resolve_kakao_friend_uuids(
                access_token=token_info["access_token"],
                requested_names=settings["kakao_friend_names"],
                requested_uuids=settings["kakao_friend_uuids"],
                timeout_seconds=settings["request_timeout_seconds"],
            )
            receiver_chunks = chunk_receiver_uuids(receiver_uuids)
        except Exception as error:
            logger.exception("Failed to resolve Kakao friend recipients: %s", error)
            return True
    else:
        receiver_chunks = [None]

    for item in discounts:
        try:
            for receiver_chunk in receiver_chunks:
                send_kakao_discount_alert(
                    access_token=token_info["access_token"],
                    item=item,
                    timeout_seconds=settings["request_timeout_seconds"],
                    receiver_uuids=receiver_chunk,
                )

            if mark_state:
                notified_at = datetime.now().astimezone().isoformat(
                    timespec="seconds"
                )
                mark_discount_notified(state, item, notified_at)
            logger.info(
                "KakaoTalk notification sent for %s via %s",
                item["title"],
                provider,
            )
        except Exception as error:
            logger.exception(
                "Failed to send KakaoTalk notification for %s: %s",
                item["title"],
                error,
            )
            errors.append(
                {
                    "target": item["title"],
                    "error": f"KakaoTalk send failed: {error}",
                }
            )
            notification_failed = True

    return notification_failed


def main() -> int:
    configure_logging()
    args = parse_args()

    try:
        settings = load_settings()
    except Exception as error:
        logger.exception("Failed to load configuration: %s", error)
        return 1

    logger.info("Loaded settings from %s", settings["settings_path"])

    state = load_state(settings["state_path"])

    if args.test_notification:
        logger.info(
            "Sending a test notification using provider: %s",
            settings["notification_provider"],
        )
        test_item = build_test_discount_item(settings)
        notification_failed = send_notifications(
            settings=settings,
            state=state,
            discounts=[test_item],
            errors=[],
            mark_state=False,
        )
        state["meta"]["last_test_notification_at"] = datetime.now().astimezone().isoformat(
            timespec="seconds"
        )
        save_state(settings["state_path"], state)
        return 1 if notification_failed else 0

    errors: list[dict[str, str]] = []
    new_discounts: list[dict[str, Any]] = []
    notification_failed = False

    session = requests.Session()
    session.headers.update(settings["request_headers"])

    try:
        apply_lezhin_session(
            session=session,
            state=state,
            email=settings.get("lezhin_email"),
            password=settings.get("lezhin_password"),
            timeout_seconds=settings["request_timeout_seconds"],
        )
    except Exception as error:
        logger.warning("레진 로그인 실패 (비로그인으로 계속 진행): %s", error)

    try:
        for target in settings["webtoons"]:
            target_name = target.get("title") or target.get("url", "unknown target")
            logger.info("Checking %s", target_name)

            try:
                result = check_webtoon(
                    target=target,
                    session=session,
                    headers=settings["request_headers"],
                    timeout_seconds=settings["request_timeout_seconds"],
                )

                entry = state["webtoons"].get(result["identifier"], {})
                current_signature = (
                    result["discount"]["signature"] if result["discount"] else None
                )
                previous_current_signature = entry.get("current_discount_signature")
                last_notified_signature = entry.get(
                    "last_notified_discount_signature"
                )

                if current_signature and (
                    current_signature != previous_current_signature
                    or current_signature != last_notified_signature
                ):
                    new_discounts.append(result)

                state["webtoons"][result["identifier"]] = {
                    "title": result["title"],
                    "url": result["url"],
                    "requested_title": result.get("requested_title"),
                    "last_checked_at": result["checked_at"],
                    "current_discount_signature": current_signature,
                    "current_discount": result["discount"],
                    "last_notified_discount_signature": last_notified_signature,
                    "last_notification_at": entry.get("last_notification_at"),
                }

                if result["discount"]:
                    logger.info(
                        "Discount found for %s: %s",
                        result["title"],
                        result["discount"]["banner_text"],
                    )
                else:
                    logger.info("No active discount found for %s", result["title"])

            except Exception as error:
                logger.exception("Failed to check %s: %s", target_name, error)
                errors.append({"target": target_name, "error": str(error)})

        notification_failed = send_notifications(
            settings=settings,
            state=state,
            discounts=new_discounts,
            errors=errors,
            mark_state=True,
        )

        state["meta"].update(
            {
                "last_run_at": datetime.now().astimezone().isoformat(
                    timespec="seconds"
                ),
                "checked_count": len(settings["webtoons"]),
                "error_count": len(errors),
            }
        )
    finally:
        save_state(settings["state_path"], state)
        session.close()

    if notification_failed:
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
