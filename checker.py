from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


LEZHIN_BASE_URL = "https://www.lezhin.com"

_DISCOUNT_PATTERNS = (
    re.compile(
        r"\[(?P<original>\d+)\s*[→>-]+\s*(?P<discounted>\d+)코인\]\s*"
        r"(?:[^()]{0,80})?(?:\((?P<period>[^()]+까지)\))?"
    ),
    re.compile(
        r"이벤트!\s*모든\s*회차\s*(?P<discounted>\d+)코인(?:\s*\((?P<period>[^()]+까지)\))?"
    ),
    re.compile(
        r"이벤트!\s*모든회차\s*(?P<discounted>\d+)코인(?:\s*\((?P<period>[^()]+까지)\))?"
    ),
    re.compile(
        r"전\s*회차\s*(?P<discounted>\d+)코인\s*할인(?:\s*\((?P<period>[^()]+까지)\))?"
    ),
)

_COMIC_PATH_PATTERN = re.compile(r"^/ko/comic/[^/?#]+/?$")
_DATE_PATTERN = re.compile(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})")
_TIME_PATTERN = re.compile(r"(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?")


def check_webtoon(
    target: dict[str, str],
    session: requests.Session,
    headers: dict[str, str],
    timeout_seconds: int,
) -> dict[str, Any]:
    resolved_url = resolve_webtoon_url(
        target=target,
        session=session,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )
    response = session.get(resolved_url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    title = extract_title(soup)
    discount = extract_discount_info(soup)

    return {
        "identifier": resolved_url,
        "title": title,
        "url": resolved_url,
        "requested_title": target.get("title"),
        "checked_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "discount": discount,
    }


def resolve_webtoon_url(
    target: dict[str, str],
    session: requests.Session,
    headers: dict[str, str],
    timeout_seconds: int,
) -> str:
    if target.get("url"):
        return target["url"]

    title = target.get("title", "").strip()
    if not title:
        raise ValueError("Webtoon target must include either url or title.")

    search_url = f"{LEZHIN_BASE_URL}/ko/search?q={quote(title)}&t=all"
    response = session.get(search_url, headers=headers, timeout=timeout_seconds)
    response.raise_for_status()
    response.encoding = response.encoding or response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")
    resolved_url = _extract_first_comic_url(soup, title)
    if not resolved_url:
        raise LookupError(f"Unable to resolve a Lezhin comic URL for title: {title}")

    return resolved_url


def extract_title(soup: BeautifulSoup) -> str:
    for heading in soup.select("h1, h2"):
        text = normalize_text(heading.get_text(" ", strip=True))
        if text:
            return text

    og_title = soup.select_one("meta[property='og:title']")
    if og_title and og_title.get("content"):
        return normalize_text(str(og_title["content"]))

    if soup.title and soup.title.string:
        return normalize_text(
            soup.title.string.replace(" - 웹툰 - 레진코믹스", "").strip()
        )

    return "Unknown title"


def extract_discount_info(soup: BeautifulSoup) -> dict[str, Any] | None:
    candidates = []
    for text in soup.stripped_strings:
        normalized = normalize_text(text)
        if "코인" in normalized and ("할인" in normalized or "이벤트" in normalized):
            candidates.append(normalized)

    for candidate in candidates:
        parsed = parse_discount_text(candidate)
        if parsed:
            return parsed

    page_text = normalize_text(soup.get_text(" ", strip=True))
    parsed = parse_discount_text(page_text)
    if parsed:
        return parsed

    return None


def parse_discount_text(text: str) -> dict[str, Any] | None:
    normalized = normalize_text(text)

    for pattern in _DISCOUNT_PATTERNS:
        match = pattern.search(normalized)
        if not match:
            continue

        original_price = (
            int(match.group("original")) if match.groupdict().get("original") else None
        )
        discounted_price = int(match.group("discounted"))
        period_text = (match.groupdict().get("period") or "").strip() or None

        return {
            "banner_text": normalized,
            "original_price": original_price,
            "discounted_price": discounted_price,
            "discount_rate": calculate_discount_rate(
                original_price=original_price,
                discounted_price=discounted_price,
            ),
            "period_text": period_text,
            "deadline_iso": parse_deadline(period_text),
            "signature": build_discount_signature(
                banner_text=normalized,
                original_price=original_price,
                discounted_price=discounted_price,
                period_text=period_text,
            ),
        }

    return None


def calculate_discount_rate(
    original_price: int | None, discounted_price: int | None
) -> int | float | None:
    if not original_price or discounted_price is None or original_price <= 0:
        return None

    rate = ((original_price - discounted_price) / original_price) * 100
    if rate.is_integer():
        return int(rate)
    return round(rate, 2)


def build_discount_signature(
    banner_text: str,
    original_price: int | None,
    discounted_price: int | None,
    period_text: str | None,
) -> str:
    parts = [
        banner_text,
        str(original_price) if original_price is not None else "",
        str(discounted_price) if discounted_price is not None else "",
        period_text or "",
    ]
    return "|".join(parts)


def parse_deadline(period_text: str | None) -> str | None:
    if not period_text:
        return None

    date_match = _DATE_PATTERN.search(period_text)
    if not date_match:
        return None

    now = datetime.now().astimezone()
    month = int(date_match.group("month"))
    day = int(date_match.group("day"))

    hour = 0
    minute = 0

    trailing_text = period_text[date_match.end() :]

    if "정오" in trailing_text:
        hour = 12
    elif "자정" in trailing_text:
        hour = 0
    else:
        time_match = _TIME_PATTERN.search(trailing_text)
        if time_match:
            hour = int(time_match.group("hour"))
            minute = int(time_match.group("minute") or "0")
            if "오후" in trailing_text and hour < 12:
                hour += 12
            if "오전" in trailing_text and hour == 12:
                hour = 0

    try:
        deadline = now.replace(
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=0,
            microsecond=0,
        )
    except ValueError:
        return None

    if deadline < now - timedelta(days=180):
        try:
            deadline = deadline.replace(year=deadline.year + 1)
        except ValueError:
            return None

    return deadline.isoformat(timespec="seconds")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_first_comic_url(soup: BeautifulSoup, title: str) -> str | None:
    exact_matches: list[str] = []
    fallback_matches: list[str] = []
    lowered_title = title.casefold()

    for anchor in soup.select("a[href]"):
        href = (anchor.get("href") or "").strip()
        if not _COMIC_PATH_PATTERN.match(href):
            continue

        absolute_url = urljoin(LEZHIN_BASE_URL, href)
        anchor_text = normalize_text(anchor.get_text(" ", strip=True))

        if anchor_text and lowered_title in anchor_text.casefold():
            exact_matches.append(absolute_url)
        else:
            fallback_matches.append(absolute_url)

    if exact_matches:
        return exact_matches[0]
    if fallback_matches:
        return fallback_matches[0]
    return None
