# -*- coding: utf-8 -*-
import base64
import binascii
import html
import json
import re
from urllib.parse import urlparse

from ...domain.models import Site, SourceDocument
from ...site_profiles.registry import (
    DYNAMIC_RECORD_AUTHOR_ALIASES,
    DYNAMIC_RECORD_SUBTOPIC_ALIASES,
    DYNAMIC_RECORD_TOPIC_ALIASES,
)
from ...text import html_to_text, normalize_text
from .routes import dynamic_record_scope

DEFAULT_KEYWORDS = ("杀半头", "秒杀半头", "必杀半头", "绝杀半头", "稳杀半头")


class DynamicBrowserFallbackRequired(ValueError):
    """Exact dynamic API is absent or empty, so browser rendering is allowed."""


def iter_target_records(value, target_id: str, path: str = "root"):
    if isinstance(value, dict):
        if str(value.get("id") or "") == target_id and any(
            key in value
            for key in (
                "content", "body", "article_content", "html", "sub_topic", "topic", "title",
            )
        ):
            yield path, value
        for key, child in value.items():
            yield from iter_target_records(child, target_id, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_target_records(child, target_id, f"{path}[{index}]")


def iter_json_payloads(document: SourceDocument):
    """Yield complete JSON payloads from one source document, never business regex hits."""
    raw = str(document)
    candidates = [raw]
    candidates.extend(
        html.unescape(match.group(1)).strip()
        for match in re.finditer(r"<script\b[^>]*>(.*?)</script\s*>", raw, re.I | re.S)
    )
    seen: set[str] = set()
    decoder = json.JSONDecoder()
    for candidate in candidates:
        if not candidate:
            continue
        payloads = [candidate]
        start = min(
            (index for index in (candidate.find("{"), candidate.find("[")) if index >= 0),
            default=-1,
        )
        if start > 0:
            payloads.append(candidate[start:])
        for payload_text in payloads:
            try:
                payload, _end = decoder.raw_decode(payload_text.lstrip())
            except (TypeError, ValueError):
                continue
            fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            if fingerprint not in seen:
                seen.add(fingerprint)
                yield payload


def dynamic_browser_fallback_allowed(error: Exception) -> bool:
    return isinstance(error, DynamicBrowserFallbackRequired) or "缺少正文内容" in str(error)


def decode_article_field(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"动态记录缺少 {field_name} 字段")
    try:
        raw = base64.b64decode(value, validate=True)
        return raw.decode("utf-8", errors="strict")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"动态记录 {field_name} 不是有效 Base64 UTF-8") from exc


def target_record_content(record: dict, record_kind: str) -> str:
    for key in ("content", "body", "article_content", "text"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value
    if record_kind == "article":
        encoded_html = record.get("html")
        if isinstance(encoded_html, str) and encoded_html.strip():
            return decode_article_field(encoded_html, "html")
    return ""


def target_record_title(record: dict, record_kind: str) -> str:
    if record_kind == "article":
        return normalize_text(decode_article_field(record.get("title"), "title"))
    for key in ("title", "topic", "sub_topic"):
        title = normalize_text(str(record.get(key) or ""))
        if title:
            return title
    raise ValueError("动态记录缺少 标题字段")


def profile_author_from_documents(
    documents: list[SourceDocument], user_id: str
) -> str:
    """Read a nickname only from the exact profile endpoint for the URL user."""
    nicknames: set[str] = set()
    profile_path = f"/api/v1/users/{user_id}"
    for document in documents:
        source_url = str(getattr(document, "source_url", ""))
        if urlparse(source_url).path.rstrip("/") != profile_path:
            continue
        for payload in iter_json_payloads(document):
            if not isinstance(payload, dict) or str(payload.get("id") or "") != user_id:
                continue
            nickname = normalize_text(str(payload.get("nickname") or ""))
            if nickname:
                nicknames.add(nickname)
    if len(nicknames) > 1:
        raise ValueError(
            f"用户资料 {user_id} 作者信息冲突：{','.join(sorted(nicknames))}"
        )
    return next(iter(nicknames), "")


def target_record_document(
    documents: list[SourceDocument], url: str, site: Site
) -> list[SourceDocument]:
    scope = dynamic_record_scope(url)
    if scope is None:
        return documents

    record_kind, target_id = scope
    records: list[tuple[SourceDocument, str, dict]] = []
    for document in documents:
        for payload in iter_json_payloads(document):
            records.extend(
                (document, path, record)
                for path, record in iter_target_records(payload, target_id)
            )

    if not records:
        raise ValueError(f"动态记录 {target_id} 未找到唯一结构化记录")
    if len(records) != 1:
        paths = ",".join(
            f"{document.source_url or '未知来源'}@{path}"
            for document, path, _record in records[:5]
        )
        raise ValueError(f"动态记录 {target_id} 匹配到多个记录：{paths}")

    source_document, path, record = records[0]
    if str(record.get("id") or "") != target_id:
        raise ValueError(f"动态记录 {target_id} ID校验失败：JSON路径 {path}")

    parsed = urlparse(url)
    user_match = re.search(r"/(?:users/)(\d+)", parsed.fragment, re.I)
    expected_user_id = user_match.group(1) if user_match else None
    if expected_user_id is not None and str(record.get("user_id") or "") != expected_user_id:
        raise ValueError(
            f"动态记录 {target_id} 用户ID校验失败："
            f"URL用户 {expected_user_id}，记录用户 {record.get('user_id')}"
        )

    declared_author_fields = {
        field: normalized
        for field in ("authorNickname", "author", "username")
        if (normalized := normalize_text(str(record.get(field) or "")))
    }
    declared_author_values = set(declared_author_fields.values())
    if len(declared_author_values) > 1:
        details = "，".join(
            f"{field}={value}" for field, value in declared_author_fields.items()
        )
        raise ValueError(f"动态记录 {target_id} 作者信息冲突：{details}")
    declared_author = next(iter(declared_author_values), "")
    nested_user = record.get("user")
    nested_author = ""
    if isinstance(nested_user, dict):
        nested_user_id = str(nested_user.get("id") or "")
        record_user_id = str(record.get("user_id") or "")
        if nested_user_id and record_user_id and nested_user_id != record_user_id:
            raise ValueError(
                f"动态记录 {target_id} 嵌套用户ID校验失败："
                f"记录用户 {record_user_id}，嵌套用户 {nested_user_id}"
            )
        if expected_user_id is not None and nested_user_id and nested_user_id != expected_user_id:
            raise ValueError(
                f"动态记录 {target_id} 嵌套用户ID校验失败："
                f"URL用户 {expected_user_id}，嵌套用户 {nested_user_id}"
            )
        nested_author = normalize_text(
            str(
                nested_user.get("nickname")
                or nested_user.get("authorNickname")
                or nested_user.get("author")
                or nested_user.get("username")
                or ""
            )
        )
    if declared_author and nested_author and declared_author != nested_author:
        raise ValueError(
            f"动态记录 {target_id} 作者信息冲突："
            f"记录作者 {declared_author}，嵌套作者 {nested_author}"
        )
    profile_author = (
        profile_author_from_documents(documents, expected_user_id)
        if expected_user_id is not None
        else ""
    )
    identity_authors = {
        author
        for author in (declared_author, nested_author, profile_author)
        if author
    }
    if len(identity_authors) > 1:
        raise ValueError(
            f"动态记录 {target_id} 作者信息冲突："
            + "，".join(sorted(identity_authors))
        )
    author = next(iter(identity_authors), "")
    allowed_authors = {
        normalize_text(site.name),
        *(normalize_text(alias) for alias in DYNAMIC_RECORD_AUTHOR_ALIASES.get(site.url, ())),
    }
    if author not in allowed_authors:
        raise ValueError(
            f"动态记录 {target_id} 作者校验失败：记录作者 {author or '缺失'}，配置站名 {site.name}"
        )

    title = target_record_title(record, record_kind)

    content = target_record_content(record, record_kind)
    if not content:
        raise ValueError(f"动态记录 {target_id} 缺少正文内容")

    if record_kind in {"reference", "forum"}:
        topic = normalize_text(str(record.get("topic") or ""))
        declared_topics = DYNAMIC_RECORD_TOPIC_ALIASES.get(site.url, ())
        if declared_topics:
            allowed_topics = {
                normalize_text(site.name),
                *(normalize_text(item) for item in declared_topics),
            }
            if topic not in allowed_topics:
                raise ValueError(
                    f"动态记录 {target_id} 栏目校验失败：记录栏目 {topic or '缺失'}，"
                    f"配置栏目 {','.join(sorted(allowed_topics))}"
                )
        allowed_subtopics = {
            normalize_text(item)
            for item in DYNAMIC_RECORD_SUBTOPIC_ALIASES.get(site.url, ())
        }
        if allowed_subtopics:
            subtopic = normalize_text(str(record.get("sub_topic") or ""))
            if subtopic not in allowed_subtopics:
                raise ValueError(
                    f"动态记录 {target_id} 子栏目校验失败："
                    f"记录子栏目 {subtopic or '缺失'}，配置子栏目 {','.join(sorted(allowed_subtopics))}"
                )

    header_values = [
        title if key == "title" else str(record.get(key) or "")
        for key in ("title", "topic", "sub_topic", "category", "column")
    ]
    header_text = normalize_text(" ".join(header_values))
    body_text = normalize_text(html_to_text(content))
    if not any(keyword in header_text for keyword in DEFAULT_KEYWORDS):
        if not any(keyword in body_text for keyword in DEFAULT_KEYWORDS):
            raise ValueError(f"动态记录 {target_id} 栏目校验失败：未找到半头栏目")
    if site.anchors and not any(anchor in header_text or anchor in body_text for anchor in site.anchors):
        raise ValueError(f"动态记录 {target_id} 专属锚点校验失败：未找到 {','.join(site.anchors)}")

    for key in ("pick", "region", "direction", "position"):
        value = normalize_text(str(record.get(key) or "")).lower()
        if value in {"top", "顶部", "上", "first"} and site.pick != "top":
            raise ValueError(f"动态记录 {target_id} 方向校验失败：记录为top，配置为{site.pick}")
        if value in {"bottom", "尾部", "底部", "下", "last"} and site.pick != "bottom":
            raise ValueError(f"动态记录 {target_id} 方向校验失败：记录为bottom，配置为{site.pick}")

    metadata = "\n".join(
        title if key == "title" else str(record.get(key) or "")
        for key in (
            "id", "user_id", "title", "topic", "sub_topic", "author", "authorNickname", "username",
        )
    )
    return [
        SourceDocument(
            f"{metadata}\n{content}",
            source_url=source_document.source_url,
            source_kind="dynamic-record",
            record_id=target_id,
            record_path=path,
            route_type=record_kind,
            url_record_id=target_id,
            api_url=source_document.source_url if source_document.source_kind == "api" else "",
            title=title,
            author=author,
            container_id=path,
            document_authority="exact-dynamic-record",
            block_start=0,
            block_end=len(f"{metadata}\n{content}"),
        )
    ]
