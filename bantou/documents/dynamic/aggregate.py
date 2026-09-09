"""Resolve one exact issue record; never convert every record into a forum."""
import json
import re
from datetime import date
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

from ...domain.models import Site
from ...fetching.policy import FetchError, fetch_text
from ...site_profiles.registry import DYNAMIC_RECORD_TOPIC_ALIASES, DYNAMIC_RECORD_SUBTOPIC_ALIASES
from ...text import html_to_text, normalize_text
from .records import DEFAULT_KEYWORDS, target_record_content
from .routes import extra_api_urls, user_aggregate_scope


def iter_user_aggregate_records(value, path="root"):
    if isinstance(value, dict):
        if "id" in value and "user_id" in value and any(key in value for key in ("content", "body", "article_content", "html", "topic", "title")):
            yield path, value
        else:
            for key, child in value.items():
                yield from iter_user_aggregate_records(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_user_aggregate_records(child, f"{path}[{index}]")


def aggregate_record_matches_request(record, user_id, requested_issue, site=None):
    if str(record.get("user_id") or "") != user_id:
        return False
    if "year" in record:
        try:
            year = int(record["year"])
        except (TypeError, ValueError) as exc:
            raise ValueError("聚合记录年度无效") from exc
        if year != date.today().year:
            return False
    try:
        if int(record.get("draw")) != requested_issue:
            return False
    except (TypeError, ValueError):
        return False
    text = normalize_text(" ".join(str(record.get(key) or "") for key in ("topic", "sub_topic", "title")) + " " + html_to_text(target_record_content(record, "forum")))
    if not re.search(rf"(?<!\d){requested_issue}\s*期(?!\d)", text):
        return False
    if not any(keyword in text for keyword in DEFAULT_KEYWORDS):
        return False
    if site is not None:
        if not any(normalize_text(anchor) in text for anchor in site.anchors):
            return False
        topics = DYNAMIC_RECORD_TOPIC_ALIASES.get(site.url, ())
        subtopics = DYNAMIC_RECORD_SUBTOPIC_ALIASES.get(site.url, ())
        if topics and normalize_text(str(record.get("topic") or "")) not in {normalize_text(site.name), *(normalize_text(t) for t in topics)}:
            return False
        if subtopics and normalize_text(str(record.get("sub_topic") or "")) not in {normalize_text(t) for t in subtopics}:
            return False
    return True


def _pages(api_url, timeout, verify_ssl, deadline):
    """Follow explicit metadata or successive pages of the declared size.

    A repeated full page, malformed metadata or exhausted limit is incomplete,
    never evidence that a candidate is unique. Unverified endpoints fail closed.
    """
    parsed = urlparse(api_url)
    seen_pages = set()
    for page in range(1, 51):
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        try:
            page_size = int(query.get("per_page", "20"))
        except ValueError as exc:
            raise ValueError("聚合接口分页大小无效") from exc
        if page_size < 1:
            raise ValueError("聚合接口分页大小无效")
        query.update(page=str(page), per_page=str(page_size))
        page_url = urlunparse(parsed._replace(query=urlencode(query)))
        payload = json.loads(fetch_text(page_url, timeout, verify_ssl, deadline=deadline))
        if isinstance(payload, list):
            rows, current, last = payload, page, None
        elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
            rows = payload["data"]
            meta = payload.get("meta", payload)
            if not isinstance(meta, dict):
                raise ValueError("聚合接口分页元数据无效")
            current = meta.get("current_page", page)
            last = meta.get("last_page")
            if type(current) is not int or current != page or (last is not None and (type(last) is not int or last < page)):
                raise ValueError("聚合接口分页编号不一致")
        else:
            raise ValueError("聚合接口没有可验证的记录列表")
        fingerprint = json.dumps(rows, ensure_ascii=False, sort_keys=True)
        if rows and fingerprint in seen_pages:
            raise ValueError("聚合接口重复返回同一页，无法证明记录完整")
        seen_pages.add(fingerprint)
        yield rows
        if (last is not None and page == last) or (last is None and len(rows) < page_size):
            return
    raise ValueError("聚合接口分页超过50页，记录唯一性核验未完成")


def resolve_user_aggregate_detail_url(site: Site, requested_issue: int, timeout: int, verify_ssl: bool, *, deadline=None) -> str:
    user_id = user_aggregate_scope(site.url)
    if user_id is None:
        raise ValueError("站点不是无ID用户聚合页")
    records = {}
    for api_url in extra_api_urls(site.url):
        path = urlparse(api_url).path
        family = next((kind for kind in ("forums", "references", "discoveries") if f"/{kind}" in path), None)
        if family is None:
            raise ValueError("未登记的聚合接口类型")
        try:
            for rows in _pages(api_url, timeout, verify_ssl, deadline):
                for record_path, record in iter_user_aggregate_records(rows):
                    if not aggregate_record_matches_request(record, user_id, requested_issue, site):
                        continue
                    record_id = str(record.get("id") or "")
                    if not record_id.isascii() or not record_id.isdigit():
                        raise ValueError("聚合记录ID无效")
                    key = (family, record_id)
                    previous = records.get(key)
                    if previous is not None and previous != record:
                        raise ValueError(f"{requested_issue}期同类型同ID记录内容冲突：{family}/{record_id}")
                    records[key] = record
        except (FetchError, json.JSONDecodeError) as exc:
            raise ValueError("用户聚合接口读取未完成，无法证明详情记录唯一") from exc
    if len(records) != 1:
        raise ValueError(f"{requested_issue}期详情记录未唯一匹配：{len(records)}条")
    family, record_id = next(iter(records))
    if family == "discoveries":
        raise ValueError("discovery详情路由尚未验证，禁止冒充forum详情")
    parsed = urlparse(site.url)
    return f"{parsed.scheme}://{parsed.netloc}/#/users/{user_id}/{family}/{record_id}"
