# -*- coding: utf-8 -*-
import html
import json
import re
from urllib.parse import urljoin, urlparse

from ..domain.models import Site, SourceDocument
from ..fetching.policy import (
    FetchError,
    fetch_interactive_rendered_html,
    fetch_rendered_html,
    fetch_rendered_text,
    fetch_resource_group,
    fetch_text,
)
from ..site_profiles.registry import (
    BABA_FORUM_URL,
    DEDICATED_RENDERED_SITE_RULES,
    DYNAMIC_RECORD_SUBTOPIC_ALIASES,
    DYNAMIC_RECORD_TOPIC_ALIASES,
    HALF_HEAD_LINK_RE,
    IFRAME_SRC_RE,
    SCRIPT_SRC_RE,
    SITE_BROWSER_HTML_URLS,
    SITE_BROWSER_HTML_WAIT_UNTIL,
    SITE_RENDERED_PAGE_AUTHORITY_URLS,
    WUZHUANXINGYI_URL,
)
from ..text import normalize_text
from ..fetching.transport import same_origin
from .content import (
    add_document_with_decoded,
    extract_dedicated_rendered_documents,
    should_fetch_half_head_link,
    should_fetch_iframe,
    should_fetch_script,
)
from .dynamic.records import DynamicBrowserFallbackRequired
from .dynamic.routes import (
    dynamic_record_scope,
    extra_api_urls,
    is_user_aggregate_api_url,
    reference_forum_urls_from_document,
)


def collect_dynamic_api_documents(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> tuple[list[SourceDocument], list[str]]:
    """Fetch an exact dynamic record API before any browser page."""
    api_urls = extra_api_urls(url)
    if not api_urls:
        raise ValueError("动态记录缺少专属接口")

    exact_api_url, *auxiliary_urls = api_urls
    try:
        exact_text = fetch_text(
            exact_api_url, timeout, verify_ssl, deadline=deadline
        )
    except FetchError as exc:
        if str(exc).startswith("HTTP 404"):
            raise DynamicBrowserFallbackRequired(
                f"动态记录专属接口返回404：{exact_api_url}"
            ) from exc
        raise
    if not exact_text.strip():
        raise DynamicBrowserFallbackRequired(
            f"动态记录专属接口正文为空：{exact_api_url}"
        )
    try:
        json.loads(exact_text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"动态记录专属接口不是可信JSON：{exact_api_url}") from exc

    documents: list[SourceDocument] = []
    seen_docs: set[tuple[str, str, str]] = set()
    script_errors: list[str] = []
    add_document_with_decoded(
        exact_text,
        documents,
        seen_docs,
        source_url=exact_api_url,
        source_kind="api",
    )
    add_fetched_resources(
        auxiliary_urls,
        timeout,
        verify_ssl,
        documents,
        seen_docs,
        script_errors,
        "api",
        deadline=deadline,
    )
    return documents, script_errors

def add_fetched_resources(
    urls: list[str],
    timeout: int,
    verify_ssl: bool,
    documents: list[SourceDocument],
    seen_docs: set[tuple[str, str, str]],
    script_errors: list[str],
    resource_kind: str,
    split_user_aggregates: bool = False,
    *,
    deadline: float | None = None,
) -> None:
    for resource_url, resource_text, resource_error in fetch_resource_group(
        urls, timeout, verify_ssl, deadline=deadline
    ):
        if resource_error is not None:
            if resource_kind in {"iframe", "script"}:
                raise FetchError(f"权威附属资源获取失败：{resource_url}：{resource_error}") from resource_error
            script_errors.append(f"{resource_url} ({resource_error})")
            continue
        if resource_text:
            if split_user_aggregates and is_user_aggregate_api_url(resource_url):
                try:
                    payload = json.loads(resource_text)
                except (TypeError, ValueError):
                    payload = None
                if isinstance(payload, list) and payload:
                    for item in payload:
                        if isinstance(item, dict):
                            add_document_with_decoded(
                                json.dumps(item, ensure_ascii=False),
                                documents,
                                seen_docs,
                                source_url=resource_url,
                                source_kind="api",
                            )
                    continue
            add_document_with_decoded(
                resource_text,
                documents,
                seen_docs,
                source_url=resource_url,
                source_kind=resource_kind,
            )


def collect_documents(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> tuple[list[SourceDocument], list[str]]:
    documents: list[SourceDocument] = []
    seen_docs: set[tuple[str, str, str]] = set()
    script_errors: list[str] = []
    script_urls: list[str] = []
    seen_scripts: set[str] = set()
    frame_urls: list[str] = []
    seen_frames: set[str] = set()
    half_head_urls: list[str] = []
    seen_half_head_urls: set[str] = set()
    forum_detail_urls: list[str] = []
    seen_forum_detail_urls: set[str] = set()

    page_html = fetch_text(url, timeout, verify_ssl, deadline=deadline)
    add_document_with_decoded(
        page_html, documents, seen_docs, source_url=url, source_kind="page"
    )

    if url in SITE_BROWSER_HTML_URLS:
        try:
            rendered_html = fetch_rendered_html(
                url,
                timeout,
                verify_ssl,
                deadline=deadline,
                wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(url, "networkidle"),
            )
        except Exception as exc:
            script_errors.append(f"浏览器 HTML 渲染失败：{exc}")
        else:
            add_document_with_decoded(
                rendered_html, documents, seen_docs, source_url=url, source_kind="browser"
            )

    add_fetched_resources(
        extra_api_urls(url),
        timeout,
        verify_ssl,
        documents,
        seen_docs,
        script_errors,
        "api",
        split_user_aggregates=True,
        deadline=deadline,
    )

    script_index = 0
    frame_index = 0
    document_scan_index = 0
    while True:
        if len(documents) > 128 or len(seen_scripts) + len(seen_frames) + len(seen_half_head_urls) > 64:
            raise ValueError("来源资源数量超过上限，未完成来源核验")
        documents_to_scan = documents[document_scan_index:]
        document_scan_index = len(documents)
        for document in documents_to_scan:
            document_url = str(getattr(document, "source_url", "") or url)
            scan_documents = (document, document.replace("\\'", "'").replace('\\"', '"'))
            for scan_document in scan_documents:
                for _, src in SCRIPT_SRC_RE.findall(scan_document):
                    if not src or src.strip("\\/") == "":
                        continue
                    full_url = urljoin(document_url, html.unescape(src))
                    if not same_origin(url, full_url):
                        raise ValueError("附属资源指向未登记的跨来源URL")
                    if full_url not in seen_scripts and should_fetch_script(full_url):
                        seen_scripts.add(full_url)
                        script_urls.append(full_url)
                for _, src in IFRAME_SRC_RE.findall(scan_document):
                    if not src or src.strip("\\/") == "":
                        continue
                    full_url = urljoin(document_url, html.unescape(src))
                    if not same_origin(url, full_url):
                        raise ValueError("附属资源指向未登记的跨来源URL")
                    if full_url not in seen_frames and should_fetch_iframe(full_url):
                        seen_frames.add(full_url)
                        frame_urls.append(full_url)
                for _, href in HALF_HEAD_LINK_RE.findall(scan_document):
                    if not href or href.strip("\\/") == "":
                        continue
                    full_url = urljoin(document_url, html.unescape(href))
                    if not same_origin(url, full_url):
                        raise ValueError("半头链接指向未登记的跨来源URL")
                    if full_url not in seen_half_head_urls and should_fetch_half_head_link(full_url):
                        seen_half_head_urls.add(full_url)
                        half_head_urls.append(full_url)
                for full_url in reference_forum_urls_from_document(url, scan_document):
                    if full_url not in seen_forum_detail_urls:
                        seen_forum_detail_urls.add(full_url)
                        forum_detail_urls.append(full_url)

        if (
            script_index >= len(script_urls)
            and frame_index >= len(frame_urls)
            and not half_head_urls
            and not forum_detail_urls
        ):
            break
        if script_index < len(script_urls):
            pending_scripts = script_urls[script_index:]
            script_index = len(script_urls)
            add_fetched_resources(
                pending_scripts, timeout, verify_ssl, documents, seen_docs, script_errors, "script",
                deadline=deadline,
            )
            continue
        if frame_index < len(frame_urls):
            pending_frames = frame_urls[frame_index:]
            frame_index = len(frame_urls)
            add_fetched_resources(
                pending_frames, timeout, verify_ssl, documents, seen_docs, script_errors, "iframe",
                deadline=deadline,
            )
            continue
        if half_head_urls:
            pending_half_head_urls = half_head_urls
            half_head_urls = []
            add_fetched_resources(
                pending_half_head_urls, timeout, verify_ssl, documents, seen_docs, script_errors, "linked-page",
                deadline=deadline,
            )
            continue
        pending_forum_detail_urls = forum_detail_urls
        forum_detail_urls = []
        add_fetched_resources(
                pending_forum_detail_urls, timeout, verify_ssl, documents, seen_docs, script_errors, "api",
                deadline=deadline,
        )
    return documents, script_errors


def resolve_mengxiaomeng_detail_url(
    site: Site,
    requested_issue: int,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> str:
    entry_url = site.fetch_url or site.url
    documents, _script_errors = collect_documents(
        entry_url, timeout, verify_ssl, deadline=deadline
    )
    link_re = re.compile(r'''<a[^>]*href\s*=\s*["']?([^"'\s>]+)["']?[^>]*>(.*?)</a>''', re.I | re.S)
    issue_re = re.compile(rf"(?<!\d){requested_issue}\s*期(?!\d)")
    entry_host = urlparse(entry_url).hostname or ""
    candidates: set[str] = set()
    for document in documents:
        source_url = str(getattr(document, "source_url", ""))
        source_kind = str(getattr(document, "source_kind", ""))
        if source_kind in {"linked-page", "api"}:
            continue
        if source_url and source_url != entry_url and source_kind not in {
            "script",
            "script-decoded",
            "iframe",
            "iframe-decoded",
        }:
            continue
        for match in link_re.finditer(document):
            href = html.unescape(match.group(1))
            anchor_text = normalize_text(re.sub(r"<[^>]+>", "", html.unescape(match.group(2))))
            compact = re.sub(r"\s+", "", anchor_text)
            if not issue_re.search(compact):
                continue
            if "半头" not in compact:
                continue
            if site.name not in compact:
                continue
            detail_url = urljoin(entry_url, href)
            if (urlparse(detail_url).hostname or "") != entry_host:
                continue
            candidates.add(detail_url)
    if len(candidates) == 1:
        return next(iter(candidates))
    if len(candidates) > 1:
        raise ValueError(
            f"找到多个指定期数入口：{requested_issue}期 + 半头 + {site.name}；"
            + "；".join(sorted(candidates))
        )
    raise ValueError(f"找不到指定期数入口：{requested_issue}期 + 半头 + {site.name}")


def resolve_wealth_reference_detail_url(
    site: Site,
    requested_issue: int,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> str:
    entry_url = site.fetch_url or site.url
    parsed = urlparse(entry_url)
    user_match = re.search(r"(?:^|/)users/(\d+)", parsed.fragment, re.I)
    if user_match is None:
        raise ValueError("财富榜入口缺少唯一用户ID")
    user_id = user_match.group(1)
    history_url = f"{parsed.scheme}://{parsed.netloc}/api/v1/users/{user_id}/references/history"
    try:
        payload = json.loads(fetch_text(history_url, timeout, verify_ssl, deadline=deadline))
    except json.JSONDecodeError as exc:
        raise ValueError("财富榜历史入口不是可信JSON") from exc
    if not isinstance(payload, list):
        raise ValueError("财富榜历史入口不是记录列表")

    allowed_topics = {
        normalize_text(site.name),
        *(normalize_text(item) for item in DYNAMIC_RECORD_TOPIC_ALIASES.get(site.url, ())),
    }
    allowed_subtopics = {
        normalize_text(item)
        for item in DYNAMIC_RECORD_SUBTOPIC_ALIASES.get(site.url, ())
    }
    candidates: list[dict] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        if str(item.get("user_id") or "") != user_id:
            continue
        try:
            draw = int(str(item.get("draw") or ""))
        except ValueError:
            continue
        if draw != requested_issue:
            continue
        topic = normalize_text(str(item.get("topic") or ""))
        subtopic = normalize_text(str(item.get("sub_topic") or ""))
        if topic not in allowed_topics or subtopic not in allowed_subtopics:
            continue
        record_id = str(item.get("id") or "")
        if record_id.isdigit():
            candidates.append(item)
    candidate_ids = sorted({str(item["id"]) for item in candidates})
    if len(candidate_ids) != 1:
        if not candidate_ids:
            raise ValueError(
                f"找不到唯一财富榜入口：{requested_issue}期 + {site.name} + 必杀半头"
            )
        raise ValueError(
            f"财富榜入口记录ID冲突：{requested_issue}期 + 必杀半头；"
            + "、".join(candidate_ids)
        )
    return f"{parsed.scheme}://{parsed.netloc}/#/users/{user_id}/references/{candidate_ids[0]}"


def collect_site_documents(
    site: Site,
    fetch_url: str,
    wanted_issues: set[int] | None,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> tuple[list[SourceDocument], list[str]]:
    if dynamic_record_scope(fetch_url) is not None:
        return collect_dynamic_api_documents(
            fetch_url, timeout, verify_ssl, deadline=deadline
        )
    if site.url == BABA_FORUM_URL:
        return collect_documents(fetch_url, timeout, verify_ssl, deadline=deadline)
    if site.url == WUZHUANXINGYI_URL:
        if not wanted_issues:
            raise ValueError("星移物换交互获取缺少目标期数")
        issue = max(wanted_issues)
        rendered_html = fetch_interactive_rendered_html(
            fetch_url,
            timeout,
            verify_ssl,
            issue,
            site.name,
            deadline=deadline,
            wait_until="load",
        )
        return [
            SourceDocument(
                rendered_html,
                source_url=fetch_url,
                source_kind="browser-interactive",
                container_id=f"interactive-card:{fetch_url}:{issue}",
                document_authority="declared-interactive-card",
                block_start=0,
                block_end=len(rendered_html),
            )
        ], []
    if (
        site.url in SITE_RENDERED_PAGE_AUTHORITY_URLS
        and site.parser_id != "wuzhuanxingyi_embedded"
    ):
        rendered_text = fetch_rendered_text(
            fetch_url, timeout, verify_ssl, deadline=deadline
        )
        return [
            SourceDocument(
                rendered_text,
                source_url=fetch_url,
                source_kind="browser-text",
                container_id=f"rendered-page:{fetch_url}",
                document_authority="declared-rendered-page",
                block_start=0,
                block_end=len(rendered_text),
            )
        ], []
    if fetch_url == site.url and site.url in DEDICATED_RENDERED_SITE_RULES:
        rendered_html = fetch_rendered_html(
            fetch_url,
            timeout,
            verify_ssl,
            deadline=deadline,
            wait_until=SITE_BROWSER_HTML_WAIT_UNTIL.get(site.url, "networkidle"),
        )
        return extract_dedicated_rendered_documents(
            rendered_html, site, wanted_issues, direction_first=True
        ), []
    return collect_documents(fetch_url, timeout, verify_ssl, deadline=deadline)


def collect_dynamic_browser_documents(
    url: str,
    timeout: int,
    verify_ssl: bool,
    *,
    deadline: float | None = None,
) -> list[SourceDocument]:
    """Browser fallback for a dynamic detail page; identity is verified later."""
    rendered_html = fetch_rendered_html(url, timeout, verify_ssl, deadline=deadline)
    return [
        SourceDocument(
            rendered_html,
            source_url=url,
            source_kind="browser",
            container_id=f"browser:{url}",
            document_authority="browser-fallback",
            block_start=0,
            block_end=len(rendered_html),
        )
    ]
