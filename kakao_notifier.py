from __future__ import annotations

import json
from typing import Any

import requests


KAKAO_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
KAKAO_MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
KAKAO_FRIENDS_URL = "https://kapi.kakao.com/v1/api/talk/friends"
KAKAO_FRIEND_MESSAGE_URL = "https://kapi.kakao.com/v1/api/talk/friends/message/default/send"
KAKAO_MESSAGE_TEXT_LIMIT = 200


def get_kakao_access_token(
    rest_api_key: str,
    refresh_tokens: list[str | None],
    client_secret: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    errors: list[str] = []

    for refresh_token in _unique_tokens(refresh_tokens):
        try:
            token_payload = refresh_kakao_access_token(
                rest_api_key=rest_api_key,
                refresh_token=refresh_token,
                client_secret=client_secret,
                timeout_seconds=timeout_seconds,
            )
            return {
                "access_token": token_payload["access_token"],
                "refresh_token": token_payload.get("refresh_token") or refresh_token,
                "refresh_token_renewed": bool(token_payload.get("refresh_token")),
                "expires_in": token_payload.get("expires_in"),
            }
        except Exception as error:
            errors.append(f"{refresh_token[:8]}...: {error}")

    raise RuntimeError(
        "Unable to refresh a Kakao access token. Tried all known refresh tokens. "
        + " | ".join(errors)
    )


def refresh_kakao_access_token(
    rest_api_key: str,
    refresh_token: str,
    client_secret: str | None,
    timeout_seconds: int,
) -> dict[str, Any]:
    data = {
        "grant_type": "refresh_token",
        "client_id": rest_api_key,
        "refresh_token": refresh_token,
    }
    if client_secret:
        data["client_secret"] = client_secret

    response = requests.post(
        KAKAO_TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
        data=data,
        timeout=timeout_seconds,
    )

    payload = response.json()
    if response.status_code >= 400:
        raise RuntimeError(payload.get("error_description") or payload.get("error"))
    if "access_token" not in payload:
        raise RuntimeError("Kakao token response did not include access_token.")

    return payload


def send_kakao_discount_alert(
    access_token: str,
    item: dict[str, Any],
    timeout_seconds: int,
    receiver_uuids: list[str] | None = None,
) -> None:
    template_object = build_kakao_template_object(item)
    request_data = {"template_object": json.dumps(template_object, ensure_ascii=False)}
    request_url = KAKAO_MEMO_SEND_URL
    if receiver_uuids:
        request_url = KAKAO_FRIEND_MESSAGE_URL
        request_data["receiver_uuids"] = json.dumps(receiver_uuids, ensure_ascii=False)

    response = requests.post(
        request_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded;charset=utf-8",
        },
        data=request_data,
        timeout=timeout_seconds,
    )

    payload = response.json()
    if response.status_code >= 400:
        raise RuntimeError(payload.get("msg") or payload.get("message") or str(payload))
    if receiver_uuids:
        failed = payload.get("failure_info") or []
        if failed:
            raise RuntimeError(f"Friend delivery failed: {failed}")
        successful = payload.get("successful_receiver_uuids") or []
        if not successful:
            raise RuntimeError(f"Unexpected Kakao friend response: {payload}")
        return
    if payload.get("result_code") != 0:
        raise RuntimeError(f"Unexpected Kakao response: {payload}")


def resolve_kakao_friend_uuids(
    access_token: str,
    requested_names: list[str],
    requested_uuids: list[str],
    timeout_seconds: int,
) -> list[str]:
    resolved_uuids = list(dict.fromkeys(requested_uuids))
    unresolved_names = {
        normalize_friend_name(name): name
        for name in requested_names
        if normalize_friend_name(name)
    }

    if not unresolved_names:
        return resolved_uuids

    offset = 0
    limit = 100

    while unresolved_names:
        response = requests.get(
            KAKAO_FRIENDS_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "offset": offset,
                "limit": limit,
                "order": "asc",
                "friend_order": "nickname",
            },
            timeout=timeout_seconds,
        )
        payload = response.json()
        if response.status_code >= 400:
            raise RuntimeError(payload.get("msg") or payload.get("message") or str(payload))

        elements = payload.get("elements") or []
        if not elements:
            break

        for friend in elements:
            nickname = normalize_friend_name(str(friend.get("profile_nickname") or ""))
            if nickname in unresolved_names:
                uuid = str(friend.get("uuid") or "").strip()
                if uuid:
                    resolved_uuids.append(uuid)
                    unresolved_names.pop(nickname, None)

        offset += len(elements)
        total_count = int(payload.get("total_count") or 0)
        if total_count and offset >= total_count:
            break

    if unresolved_names:
        missing_names = ", ".join(sorted(unresolved_names.values()))
        raise LookupError(
            "Could not resolve Kakao friend UUIDs for: " + missing_names
        )

    return list(dict.fromkeys(resolved_uuids))


def build_kakao_template_object(item: dict[str, Any]) -> dict[str, Any]:
    webtoon_url = item["url"]
    return {
        "object_type": "text",
        "text": build_kakao_message_text(item),
        "link": {
            "web_url": webtoon_url,
            "mobile_web_url": webtoon_url,
        },
        "button_title": "웹툰 보기",
    }


def build_kakao_message_text(item: dict[str, Any]) -> str:
    discount = item["discount"] or {}
    title = _truncate(item["title"], 70)
    lines = [f"[레진 할인] {title}"]

    discounted_price = discount.get("discounted_price")
    if discounted_price is not None:
        lines.append(f"할인가: {discounted_price}코인")

    original_price = discount.get("original_price")
    discount_rate = discount.get("discount_rate")
    if original_price is not None and discount_rate is not None:
        lines.append(f"정가: {original_price}코인 ({discount_rate}%)")
    elif discount_rate is not None:
        lines.append(f"할인율: {discount_rate}%")
    elif original_price is not None:
        lines.append(f"정가: {original_price}코인")

    period_text = discount.get("period_text")
    if period_text:
        lines.append(f"기간: {_truncate(period_text, 60)}")

    message = "\n".join(lines)
    if len(message) <= KAKAO_MESSAGE_TEXT_LIMIT:
        return message

    compact_lines = lines[:3]
    compact_message = "\n".join(compact_lines)
    if len(compact_message) <= KAKAO_MESSAGE_TEXT_LIMIT:
        return compact_message

    return _truncate(compact_message, KAKAO_MESSAGE_TEXT_LIMIT)


def chunk_receiver_uuids(receiver_uuids: list[str], chunk_size: int = 5) -> list[list[str]]:
    return [
        receiver_uuids[index : index + chunk_size]
        for index in range(0, len(receiver_uuids), chunk_size)
    ]


def normalize_friend_name(value: str) -> str:
    return " ".join(value.split()).casefold()


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return value[: max_length - 3] + "..."


def _unique_tokens(tokens: list[str | None]) -> list[str]:
    seen: set[str] = set()
    unique_tokens: list[str] = []

    for token in tokens:
        if not token:
            continue
        if token in seen:
            continue
        seen.add(token)
        unique_tokens.append(token)

    return unique_tokens
