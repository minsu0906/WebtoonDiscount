from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# 레진 로그인 엔드포인트 (변경 시 여기만 수정)
LEZHIN_LOGIN_URL = "https://www.lezhin.com/lz/api/auth/login"

# 쿠키 유효 시간 (시간 단위) — 이 시간 안이면 재로그인 생략
_COOKIE_TTL_HOURS = 12


def _is_session_fresh(lezhin_state: dict[str, Any]) -> bool:
    cached_at = lezhin_state.get("cached_at")
    if not cached_at:
        return False
    try:
        age = datetime.now().astimezone() - datetime.fromisoformat(cached_at)
        return age < timedelta(hours=_COOKIE_TTL_HOURS)
    except (ValueError, TypeError):
        return False


def _do_login(
    email: str,
    password: str,
    session: requests.Session,
    timeout_seconds: int,
) -> dict[str, str]:
    """레진 로그인 후 쿠키 딕셔너리 반환."""
    response = session.post(
        LEZHIN_LOGIN_URL,
        json={"email": email, "password": password},
        timeout=timeout_seconds,
    )
    response.raise_for_status()

    cookies = dict(session.cookies)
    if not cookies:
        raise ValueError(
            "로그인은 성공했지만 세션 쿠키가 없습니다. "
            "LEZHIN_LOGIN_URL 엔드포인트를 확인하세요."
        )
    return cookies


def apply_lezhin_session(
    session: requests.Session,
    state: dict[str, Any],
    email: str | None,
    password: str | None,
    timeout_seconds: int,
) -> None:
    """캐시된 쿠키 또는 신규 로그인 결과를 session에 적용.

    email/password가 없으면 경고만 출력하고 계속 진행.
    (비성인 작품은 로그인 없이도 동작)
    """
    lezhin_state = state.setdefault("lezhin", {})

    # 캐시 유효 → 재사용
    if _is_session_fresh(lezhin_state):
        cached_cookies = lezhin_state.get("cookies", {})
        if cached_cookies:
            session.cookies.update(cached_cookies)
            logger.info("레진 세션 캐시 재사용 (로그인 생략)")
            return

    # 자격증명 없음 → 경고 후 비로그인 진행
    if not email or not password:
        logger.warning(
            "LEZHIN_EMAIL 또는 LEZHIN_PASSWORD 미설정. "
            "성인 작품 페이지가 정상적으로 조회되지 않을 수 있습니다."
        )
        return

    # 신규 로그인
    logger.info("레진 로그인 시도: %s", email)
    cookies = _do_login(
        email=email,
        password=password,
        session=session,
        timeout_seconds=timeout_seconds,
    )
    session.cookies.update(cookies)

    lezhin_state["cookies"] = cookies
    lezhin_state["cached_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
    logger.info("레진 로그인 성공. 쿠키 state.json 캐시 완료.")
