from __future__ import annotations

import json
import os
from typing import Any


BASE_DIR = os.path.dirname(__file__)
DEFAULT_SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")
DEFAULT_STATE_PATH = os.path.join(BASE_DIR, "state.json")
DEFAULT_REQUEST_TIMEOUT_SECONDS = 20
DEFAULT_SMTP_HOST = "smtp.gmail.com"
DEFAULT_SMTP_PORT = 587


def _split_env_items(raw_value: str) -> list[str]:
    normalized = raw_value.replace(",", "\n")
    return [item.strip() for item in normalized.splitlines() if item.strip()]


def _normalize_webtoon_entry(entry: Any) -> dict[str, str]:
    if isinstance(entry, str):
        value = entry.strip()
        if not value:
            raise ValueError("Webtoon list contains an empty string entry.")

        if value.startswith(("http://", "https://")):
            return {"url": value}

        return {"title": value}

    if isinstance(entry, dict):
        url = str(entry.get("url") or "").strip()
        title = str(entry.get("title") or entry.get("name") or "").strip()

        if not url and not title:
            raise ValueError(
                "Each webtoon entry must contain at least one of: url, title."
            )

        normalized: dict[str, str] = {}
        if url:
            normalized["url"] = url
        if title:
            normalized["title"] = title
        return normalized

    raise ValueError(
        "Webtoon entries must be strings or objects with url/title fields."
    )


def _deduplicate_webtoons(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique_entries: list[dict[str, str]] = []

    for entry in entries:
        key = (entry.get("url", ""), entry.get("title", ""))
        if key in seen:
            continue
        seen.add(key)
        unique_entries.append(entry)

    return unique_entries


def _read_json_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict):
        raise ValueError(f"Settings file must contain a JSON object: {path}")

    return payload


def _get_nested_dict(data: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key, {})

    return current if isinstance(current, dict) else {}


def _get_nested_value(data: dict[str, Any], *keys: str) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def load_string_list_env(env_name: str) -> list[str]:
    raw_value = os.getenv(env_name, "").strip()
    if not raw_value:
        return []

    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
    except json.JSONDecodeError:
        pass

    return _split_env_items(raw_value)


def _load_string_list_config(data: Any, field_name: str) -> list[str]:
    if data is None:
        return []
    if not isinstance(data, list):
        raise ValueError(f"{field_name} in settings.json must be a list.")
    return [str(item).strip() for item in data if str(item).strip()]


def _load_webtoons(settings_file_data: dict[str, Any]) -> list[dict[str, str]]:
    raw_value = os.getenv("LEZHIN_WEBTOONS", "").strip()

    if raw_value:
        entries: list[Any]
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list):
                entries = parsed
            else:
                raise ValueError("LEZHIN_WEBTOONS JSON value must be a list.")
        except json.JSONDecodeError:
            entries = _split_env_items(raw_value)
    else:
        entries = settings_file_data.get("webtoons") or settings_file_data.get(
            "watchlist"
        ) or []

    if not entries:
        raise ValueError(
            "No webtoons configured. Edit settings.json or set LEZHIN_WEBTOONS."
        )

    normalized_entries = [_normalize_webtoon_entry(entry) for entry in entries]
    return _deduplicate_webtoons(normalized_entries)


def _pick_string_setting(env_name: str, config_value: Any, fallback: str = "") -> str:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value

    if config_value is None:
        return fallback

    value = str(config_value).strip()
    return value or fallback


def _pick_int_setting(env_name: str, config_value: Any, fallback: int) -> int:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return int(env_value)
    if config_value in (None, ""):
        return fallback
    return int(config_value)


def _resolve_settings_relative_path(base_dir: str, raw_path: str) -> str:
    if os.path.isabs(raw_path):
        return raw_path
    return os.path.normpath(os.path.join(base_dir, raw_path))


def load_settings() -> dict[str, Any]:
    settings_path = os.path.abspath(os.getenv("SETTINGS_PATH", DEFAULT_SETTINGS_PATH))
    settings_dir = os.path.dirname(settings_path)
    settings_file_data = _read_json_file(settings_path)
    notification_config = _get_nested_dict(settings_file_data, "notification")
    email_config = _get_nested_dict(settings_file_data, "notification", "email")
    kakao_friends_config = _get_nested_dict(
        settings_file_data, "notification", "kakao_friends"
    )
    runtime_config = _get_nested_dict(settings_file_data, "runtime")

    notification_provider = _pick_string_setting(
        "NOTIFICATION_PROVIDER",
        notification_config.get("provider"),
        "kakao_me",
    ).lower()
    if notification_provider == "kakao_friend":
        notification_provider = "kakao_friends"

    email_recipients = load_string_list_env("EMAIL_RECIPIENTS")
    if not email_recipients:
        email_recipients = _load_string_list_config(
            email_config.get("recipients"), "notification.email.recipients"
        )

    email_sender = _pick_string_setting(
        "EMAIL_SENDER",
        email_config.get("sender"),
        os.getenv("GMAIL_ADDRESS", "").strip(),
    )
    email_app_password = _pick_string_setting(
        "EMAIL_APP_PASSWORD",
        None,
        os.getenv("GMAIL_APP_PASSWORD", "").strip(),
    )
    if not email_recipients and email_sender:
        email_recipients = [email_sender]

    kakao_friend_uuids = load_string_list_env("KAKAO_FRIEND_UUIDS")
    if not kakao_friend_uuids:
        kakao_friend_uuids = _load_string_list_config(
            kakao_friends_config.get("uuids"),
            "notification.kakao_friends.uuids",
        )

    kakao_friend_names = load_string_list_env("KAKAO_FRIEND_NAMES")
    if not kakao_friend_names:
        kakao_friend_names = _load_string_list_config(
            kakao_friends_config.get("names"),
            "notification.kakao_friends.names",
        )

    state_path = _pick_string_setting(
        "STATE_PATH",
        runtime_config.get("state_path"),
        DEFAULT_STATE_PATH,
    )
    if not os.getenv("STATE_PATH", "").strip():
        state_path = _resolve_settings_relative_path(settings_dir, state_path)

    settings = {
        "settings_path": settings_path,
        "webtoons": _load_webtoons(settings_file_data),
        "notification_provider": notification_provider,
        "kakao_rest_api_key": _pick_string_setting(
            "KAKAO_REST_API_KEY",
            _get_nested_value(settings_file_data, "notification", "kakao", "rest_api_key"),
        ),
        "kakao_client_secret": _pick_string_setting(
            "KAKAO_CLIENT_SECRET",
            _get_nested_value(settings_file_data, "notification", "kakao", "client_secret"),
        )
        or None,
        "kakao_refresh_token": _pick_string_setting(
            "KAKAO_REFRESH_TOKEN",
            None,
        ),
        "kakao_friend_uuids": kakao_friend_uuids,
        "kakao_friend_names": kakao_friend_names,
        "email_sender": email_sender,
        "email_app_password": email_app_password,
        "email_recipients": email_recipients,
        "smtp_host": _pick_string_setting(
            "SMTP_HOST",
            email_config.get("smtp_host"),
            os.getenv("GMAIL_SMTP_HOST", DEFAULT_SMTP_HOST).strip()
            or DEFAULT_SMTP_HOST,
        ),
        "smtp_port": _pick_int_setting(
            "SMTP_PORT",
            email_config.get("smtp_port"),
            int(os.getenv("GMAIL_SMTP_PORT", str(DEFAULT_SMTP_PORT))),
        ),
        "state_path": state_path,
        "request_timeout_seconds": _pick_int_setting(
            "REQUEST_TIMEOUT_SECONDS",
            runtime_config.get("request_timeout_seconds"),
            DEFAULT_REQUEST_TIMEOUT_SECONDS,
        ),
        "lezhin_email": _pick_string_setting("LEZHIN_EMAIL", None) or None,
        "lezhin_password": _pick_string_setting("LEZHIN_PASSWORD", None) or None,
        "request_headers": {
            "User-Agent": os.getenv(
                "LEZHIN_USER_AGENT",
                (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    }

    supported_providers = {"email", "kakao_me", "kakao_friends"}
    if notification_provider not in supported_providers:
        raise ValueError(
            "NOTIFICATION_PROVIDER must be one of: email, kakao_me, kakao_friends."
        )

    missing = []
    if notification_provider == "email":
        if not email_sender:
            missing.append("EMAIL_SENDER or notification.email.sender")
        if not email_app_password:
            missing.append("EMAIL_APP_PASSWORD")
        if not email_recipients:
            missing.append("EMAIL_RECIPIENTS or notification.email.recipients")
    else:
        if not settings["kakao_rest_api_key"]:
            missing.append("KAKAO_REST_API_KEY")
        if not settings["kakao_refresh_token"]:
            missing.append("KAKAO_REFRESH_TOKEN")
        if notification_provider == "kakao_friends" and not (
            kakao_friend_uuids or kakao_friend_names
        ):
            missing.append(
                "KAKAO_FRIEND_UUIDS, KAKAO_FRIEND_NAMES, or notification.kakao_friends"
            )

    if missing:
        raise ValueError(
            "Missing required notification configuration: "
            + ", ".join(missing)
            + ". Edit settings.json for easy-to-change values and use env vars for secrets."
        )

    return settings
