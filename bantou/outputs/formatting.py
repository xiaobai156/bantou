# -*- coding: utf-8 -*-
"""Formatting and parsing helpers for the formal half-head outputs."""

from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

from ..domain.models import Site
from ..paths import FAILURE_RESULT_DIR, RESULT_DIR
from ..text import VALUE_RE, normalize_text

LEGACY_SUCCESS_FOOTER_LINES = ("帅铁", "白少华")


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
    detailed = " ".join(detailed_failure_reason(reason).split())
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
        if stripped.startswith("======") or stripped in {
            "内容\t次数\t排名",
            "排名\t内容\t数量",
        }:
            break
        if (
            not stripped
            or stripped in LEGACY_SUCCESS_FOOTER_LINES
            or stripped.startswith("排名\t")
        ):
            continue
        parts = stripped.split(maxsplit=1)
        if len(parts) >= 2 and VALUE_RE.fullmatch(normalize_text(parts[0])):
            rows.append((parts[1].strip(), issue_text, parts[0].strip(), ""))
    return rows


def read_success_data_strict(
    path: Path,
    issue_text: str,
    configured_sites: list[Site],
) -> list[tuple[str, str, str, str]]:
    """Read a formal success file without silently dropping damaged rows."""
    if not path.exists():
        # A formal run may have produced only a failure file because every site
        # failed. Retry then starts from an empty success set.
        return []
    expected_name = f"{issue_text}-半头.txt"
    if path.name != expected_name:
        raise ValueError(f"成功文件名与目标期不一致：期望 {expected_name}，实际 {path.name}")
    by_name = {site.name: site for site in configured_sites}
    if len(by_name) != len(configured_sites):
        raise ValueError("正式配置站点名称不唯一")

    rows: list[tuple[str, str, str, str]] = []
    ranking_lines: list[str] = []
    seen_names: set[str] = set()
    in_ranking = False
    saw_ranking_header = False
    for line_number, raw in enumerate(
        path.read_text(encoding="utf-8-sig").splitlines(), start=1
    ):
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped in LEGACY_SUCCESS_FOOTER_LINES and not in_ranking:
            continue
        if stripped in {"内容\t次数\t排名", "排名\t内容\t数量"}:
            if saw_ranking_header:
                raise ValueError(f"成功文件第{line_number}行重复排行榜表头")
            saw_ranking_header = True
            in_ranking = True
            continue
        if stripped.startswith("======"):
            raise ValueError(f"成功文件第{line_number}行包含未知分隔内容")
        if not in_ranking:
            parts = stripped.split(maxsplit=1)
            if len(parts) != 2:
                raise ValueError(f"成功文件第{line_number}行格式无效")
            value_text, site_name = parts[0], parts[1].strip()
            value_match = VALUE_RE.fullmatch(normalize_text(value_text))
            if value_match is None:
                raise ValueError(f"成功文件第{line_number}行半头值无效")
            value = f"{int(value_match.group(1))}头{value_match.group(2)}"
            if normalize_text(value_text) != value:
                raise ValueError(f"成功文件第{line_number}行半头值不是规范格式")
            if site_name not in by_name:
                raise ValueError(f"成功文件第{line_number}行站点不在正式配置：{site_name}")
            if site_name in seen_names:
                raise ValueError(f"成功文件站点重复：{site_name}")
            seen_names.add(site_name)
            rows.append((site_name, issue_text, value, by_name[site_name].url))
            continue
        parts = stripped.split("\t")
        if len(parts) != 3:
            raise ValueError(f"成功文件第{line_number}行排行榜格式无效")
        value_text, count_text, rank_text = parts
        value_match = VALUE_RE.fullmatch(normalize_text(value_text))
        if value_match is None or not count_text.isdigit() or not rank_text.isdigit():
            raise ValueError(f"成功文件第{line_number}行排行榜内容无效")
        value = f"{int(value_match.group(1))}头{value_match.group(2)}"
        ranking_lines.append(f"{value}\t{int(count_text)}\t{int(rank_text)}")

    if rows and not saw_ranking_header:
        raise ValueError("成功文件缺少排行榜，拒绝在不完整文件上重抓合并")
    expected_rankings = build_rank_lines(rows)
    if ranking_lines != expected_rankings[1:]:
        raise ValueError("成功文件排行榜与网站数据不一致")
    return rows


def read_fail_entries(path: Path) -> list[tuple[str, str, str, str]]:
    if not path.exists():
        return []
    return read_fail_entries_from_lines(path.read_text(encoding="utf-8-sig").splitlines())


def read_fail_entries_from_lines(lines: list[str]) -> list[tuple[str, str, str, str]]:
    if not lines:
        return []
    reader = csv.DictReader(io.StringIO("\n".join(lines)), delimiter="\t")
    fields = ("网站名称", "分类", "原因", "网址")
    if reader.fieldnames is None or not set(fields) <= set(reader.fieldnames):
        raise ValueError("失败文件表头无效")
    entries = []
    for row in reader:
        name = str(row.get("网站名称") or "").strip()
        if not name or name.startswith("无失败"):
            continue
        if None in row or any(row.get(field) is None for field in fields):
            raise ValueError(f"失败文件第{reader.line_num}行字段数量无效")
        entries.append(tuple(str(row[field]).strip() for field in fields))
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


def build_rank_lines(rows: list[tuple[str, str, str, str]]) -> list[str]:
    if not rows:
        return []
    by_value: dict[str, list[str]] = {}
    for site_name, _issue_text, value, _url in rows:
        by_value.setdefault(value, []).append(site_name)
    lines = ["内容\t次数\t排名"]
    rank = 0
    previous_count = None
    for value, site_names in sorted(
        by_value.items(), key=lambda item: (-len(item[1]), item[0])
    ):
        count = len(site_names)
        if count != previous_count:
            rank += 1
            previous_count = count
        lines.append(f"{value}\t{count}\t{rank}")
    return lines


def build_success_output_lines(rows: list[tuple[str, str, str, str]]) -> list[str]:
    data_lines = [f"{value} {site_name}" for site_name, _issue_text, value, _url in rows]
    rankings = build_rank_lines(rows)
    return data_lines + ([""] + rankings if rankings else [])


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass
