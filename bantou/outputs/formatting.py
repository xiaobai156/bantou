# -*- coding: utf-8 -*-
"""Formatting and parsing helpers for the formal half-head outputs."""

from __future__ import annotations

import re
import sys
from pathlib import Path

from ..domain import Site
from ..paths import FAILURE_RESULT_DIR, RESULT_DIR
from ..text import VALUE_RE, normalize_text
from .transaction import write_transaction


def failure_category(reason: str) -> str:
    normalized = normalize_text(reason)
    if not normalized or normalized == "无失败":
        return ""
    if "404" in normalized:
        return "页面不存在"
    if "403" in normalized:
        return "访问被拒绝"
    if "getaddrinfo" in normalized or "Name or service not known" in normalized:
        return "域名解析失败"
    if "超时" in normalized or "timed out" in normalized:
        return "访问超时"
    if any(marker in normalized for marker in ("SSL", "TLS", "handshake", "UNEXPECTED_EOF", "连接重置")):
        return "连接被断开"
    if "动态记录" in normalized or "记录ID" in normalized:
        return "动态记录校验失败"
    if "文档" in normalized and "冲突" in normalized:
        return "文档边界冲突"
    if "边界不是指定期" in normalized:
        return "方向越界"
    if any(
        marker in normalized
        for marker in ("方向候选冲突", "同期候选冲突", "边界候选冲突")
    ):
        return "方向候选冲突"
    if "候选内未找到" in normalized or "缺少" in normalized:
        return "期数不存在"
    if "栏目" in normalized or "锚点" in normalized:
        return "栏目没找到"
    if "字段" in normalized or "格式" in normalized or "半头" in normalized:
        return "字段校验失败"
    if "缓存" in normalized:
        return "缓存冲突"
    if "打开失败" in normalized:
        return "网站打不开"
    return "其他失败"


def detailed_failure_reason(reason: str) -> str:
    normalized = normalize_text(reason)
    if not normalized:
        return "未写入成功结果：抓取流程没有返回明确失败原因，已按失败处理"
    if normalized in {"失败", "抓取失败", "未知", "未知错误", "MISS"}:
        return f"未写入成功结果：原始原因只有“{normalized}”，已按失败处理"
    return normalized


def fail_line(site: Site, reason: str) -> str:
    detailed = detailed_failure_reason(reason)
    return f"{site.name}\t{failure_category(detailed)}\t{detailed}\t{site.url}"


def append_script_error(reason: str, script_errors_count: int) -> str:
    if script_errors_count:
        return f"{reason}；另有 {script_errors_count} 个脚本/iframe加载失败"
    return reason


def read_success_data(path: Path, issue_text: str) -> list[tuple[str, str, str, str]]:
    if not path.exists():
        return []
    rows: list[tuple[str, str, str, str]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped == "帅铁" or stripped.startswith("======") or stripped.startswith("排名\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and VALUE_RE.fullmatch(normalize_text(parts[0])):
            rows.append((parts[1].strip(), issue_text, parts[0].strip(), ""))
    return rows


def read_fail_entries(path: Path) -> list[tuple[str, str, str, str]]:
    if not path.exists():
        return []
    return read_fail_entries_from_lines(path.read_text(encoding="utf-8-sig").splitlines())


def read_fail_entries_from_lines(lines: list[str]) -> list[tuple[str, str, str, str]]:
    entries: list[tuple[str, str, str, str]] = []
    for line in lines[1:]:
        if not line.strip() or line.startswith("无失败"):
            continue
        parts = line.split("\t")
        if len(parts) >= 4:
            entries.append((parts[0], parts[1], parts[2], parts[3]))
    return entries


def spaced_failure_lines(lines: list[str]) -> list[str]:
    if not lines:
        return []
    formatted = [lines[0]]
    for index, line in enumerate(line for line in lines[1:] if line.strip()):
        if index:
            formatted.append("")
        formatted.append(line)
    return formatted


def write_failure_lines(path: Path, lines: list[str]) -> None:
    formatted = spaced_failure_lines(lines)
    if len(formatted) <= 1:
        write_transaction({path: None})
        return
    write_transaction({path: ("\n".join(formatted) + "\n").encode("utf-8-sig")})


def output_path(value: str, base_dir: Path = RESULT_DIR) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / path


def default_output_names(issues_label: str) -> tuple[str, str]:
    return f"{issues_label}期-半头.txt", f"{issues_label}期-半头-失败.txt"


def default_fail_path_for_issues(issues_label: str, override: str = "") -> Path:
    _success_name, fail_name = default_output_names(issues_label)
    return output_path(override or fail_name, FAILURE_RESULT_DIR)


def issue_sort_key(issue_text: str) -> int:
    match = re.search(r"\d+", issue_text)
    return int(match.group(0)) if match else 0


def build_rank_lines(rows: list[tuple[str, str, str, str]], title: str = "当前排行榜") -> list[str]:
    if not rows:
        return []
    by_value: dict[str, list[str]] = {}
    for site_name, _issue_text, value, _url in rows:
        by_value.setdefault(value, []).append(site_name)
    lines = [f"====== {title} ======", "排名\t内容\t数量"]
    for rank, (value, site_names) in enumerate(
        sorted(by_value.items(), key=lambda item: (-len(item[1]), item[0])), start=1
    ):
        lines.append(f"{rank}\t{value}\t{len(site_names)}")
    return lines


def build_success_output_lines(rows: list[tuple[str, str, str, str]]) -> list[str]:
    data_lines = [f"{value}\t{site_name}" for site_name, _issue_text, value, _url in rows]
    rankings = build_rank_lines(rows)
    return data_lines + (["帅铁"] + rankings if rankings else [])


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
