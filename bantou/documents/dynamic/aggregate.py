# -*- coding: utf-8 -*-
import json
import re
from urllib.parse import urlparse

from ...domain.models import Site
from ...fetching.policy import FetchError, fetch_text
from ...text import html_to_text, normalize_text
from .records import DEFAULT_KEYWORDS, target_record_content
from .routes import extra_api_urls, user_aggregate_scope


def iter_user_aggregate_records(value, path: str = "root"):
    if isinstance(value, dict):
        if "id" in value and "user_id" in value and any(
            key in value for key in ("content", "body", "article_content", "html", "topic", "title")
        ):
            yield path, value
        for key, child in value.items():
            yield from iter_user_aggregate_records(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_user_aggregate_records(child, f"{path}[{index}]")


def aggregate_record_matches_request(record: dict, user_id: str, requested_issue: int) -> bool:
    if str(record.get("user_id") or "") != user_id:
        return False
    try:
        if int(record.get("draw")) != requested_issue:
            return False
    except (TypeError, ValueError):
        return False

    content = target_record_content(record, "forum")
    record_text = normalize_text(
        " ".join(str(record.get(key) or "") for key in ("topic", "sub_topic", "title"))
        + " "
        + html_to_text(content)
    )
    if not re.search(rf"(?<!\d){requested_issue}期(?!\d)", record_text):
        return False
    return any(keyword in record_text for keyword in DEFAULT_KEYWORDS)


def resolve_user_aggregate_detail_url(
    site: Site,
    requested_issue: int,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> str:
    user_id = user_aggregate_scope(site.url)
    if user_id is None:
        raise ValueError(f"站点不是无ID用户聚合页：{site.url}")

    records_by_id: dict[str, tuple[str, dict]] = {}
    errors: list[str] = []
    api_urls = extra_api_urls(site.url)

    def scan_api_urls(urls: list[str]) -> None:
        for api_url in urls:
            try:
                payload = json.loads(
                    fetch_text(api_url, timeout, verify_ssl, deadline=deadline)
                )
            except (FetchError, json.JSONDecodeError) as exc:
                errors.append(f"{api_url}: {type(exc).__name__}: {exc}")
                continue
            for path, record in iter_user_aggregate_records(payload):
                if not aggregate_record_matches_request(record, user_id, requested_issue):
                    continue
                record_id = str(record.get("id") or "")
                if not record_id:
                    continue
                previous = records_by_id.get(record_id)
                if previous is not None:
                    previous_payload = json.dumps(previous[1], ensure_ascii=False, sort_keys=True)
                    current_payload = json.dumps(record, ensure_ascii=False, sort_keys=True)
                    if previous_payload != current_payload:
                        raise ValueError(
                            f"{requested_issue}期同一记录ID {record_id} 在接口中内容冲突"
                        )
                    continue
                records_by_id[record_id] = (path, record)

    scan_api_urls(api_urls)
    if not records_by_id:
        expanded_api_urls = [api_url.replace("per_page=20", "per_page=1000") for api_url in api_urls]
        if expanded_api_urls != api_urls:
            scan_api_urls(expanded_api_urls)

    if errors:
        raise ValueError(
            "用户聚合接口抓取或JSON校验未完成，无法证明详情记录唯一："
            + "；".join(errors[:2])
        )

    if not records_by_id:
        raise ValueError(
            f"用户聚合接口未找到 {requested_issue}期 + 半头栏目 + 唯一详情记录"
        )
    if len(records_by_id) != 1:
        details = ",".join(
            f"ID={record_id}@{path}" for record_id, (path, _record) in records_by_id.items()
        )
        raise ValueError(f"{requested_issue}期匹配到多个详情记录，拒绝按首篇选择：{details}")

    record_id = next(iter(records_by_id))
    parsed = urlparse(site.url)
    return f"{parsed.scheme}://{parsed.netloc}/#/users/{user_id}/forums/{record_id}"
