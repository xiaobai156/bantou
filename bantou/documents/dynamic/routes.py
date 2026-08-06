# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import urlparse


def dynamic_record_scope(url: str) -> tuple[str, str] | None:
    parsed = urlparse(url)
    locations = (parsed.fragment, parsed.path)
    for location in locations:
        if not location:
            continue
        match = re.search(r"/(?:users/\d+/)?references/(\d+)(?:/|$)", location, re.I)
        if match:
            return "reference", match.group(1)
        match = re.search(r"/(?:users/\d+/)?forums/(\d+)(?:/|$)", location, re.I)
        if match:
            return "forum", match.group(1)
        match = re.search(
            r"/article/(?:admin|manager)/([^/?#]+?)(?:\.html)?(?:/|$)",
            location,
            re.I,
        )
        if match:
            return "article", match.group(1)
    return None


def is_user_aggregate_api_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return bool(re.search(r"/api/v1/users/\d+/(?:forums|discoveries|references)(?:/history)?$", path))


def user_aggregate_scope(url: str) -> str | None:
    fragment = urlparse(url).fragment
    match = re.fullmatch(r"/users/(\d+)/?", fragment, re.I)
    return match.group(1) if match else None


def is_user_aggregate_page_without_record_id(url: str) -> bool:
    return user_aggregate_scope(url) is not None


def extra_api_urls(url: str) -> list[str]:
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    urls: list[str] = []
    user_match = re.search(r"(?:^|/)users/(\d+)", parsed.fragment)
    user_id = user_match.group(1) if user_match else None

    record_scope = dynamic_record_scope(url)
    if record_scope is not None:
        record_kind, record_id = record_scope
        if record_kind in {"reference", "forum"}:
            user_forum_match = re.search(
                r"/(?:users/)(\d+)/forums/(\d+)(?:/|$)", parsed.fragment, re.I
            )
            if record_kind == "forum" and user_forum_match and user_forum_match.group(2) == record_id:
                urls.append(
                    f"{base}/api/v1/users/{user_forum_match.group(1)}/forums?per_page=1000"
                )
            else:
                urls.append(f"{base}/api/v1/forums/{record_id}")
        elif record_kind == "article":
            urls.append(f"{base}/api/proxy/manager-articles/{record_id}")
        if user_id is not None:
            urls.append(f"{base}/api/v1/users/{user_id}")
        return urls

    if user_id is not None:
        urls.extend(
            [
                f"{base}/api/v1/users/{user_id}/forums?per_page=20",
                f"{base}/api/v1/users/{user_id}/discoveries?per_page=20",
                f"{base}/api/v1/users/{user_id}/references?per_page=20",
                f"{base}/api/v1/users/{user_id}/references/history",
            ]
        )

    forum_match = re.search(r"(?:^|/)forums/(\d+)", parsed.fragment)
    if forum_match:
        forum_id = forum_match.group(1)
        urls.extend(
            [
                f"{base}/api/v1/forums/{forum_id}",
                f"{base}/api/v1/forums/{forum_id}/comments?per_page=20&page=1",
            ]
        )
    return urls


def reference_forum_urls_from_document(url: str, document: str) -> list[str]:
    if dynamic_record_scope(url) is not None:
        return []
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    try:
        data = json.loads(document)
    except Exception:
        return []

    items: list[dict] = []

    def collect(value):
        if isinstance(value, dict):
            if "id" in value and "sub_topic" in value:
                items.append(value)
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(data)
    half_head_items = [
        item for item in items if "必杀半头" in str(item.get("sub_topic") or "")
    ]
    half_head_items.sort(
        key=lambda item: (
            int(item.get("draw") or 0),
            str(item.get("created_at") or ""),
            int(item.get("id") or 0),
        ),
        reverse=True,
    )
    return [
        f"{base}/api/v1/forums/{int(item['id'])}"
        for item in half_head_items
        if str(item.get("id") or "").isdigit()
    ]
