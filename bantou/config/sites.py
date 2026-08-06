import json
import re
from pathlib import Path
from urllib.parse import urlparse, urlsplit, urlunsplit

from ..domain import Site
from ..paths import PROJECT_DIR
from ..site_profiles import (
    CAIYUNTONG_URL,
    GUANGDONG_BAER_URL,
    SHENZHEN_FUTAN_URL,
    WUZHUANXINGYI_URL,
    SEWAI_TAOYUAN_URL,
    SUPPORTED_PARSER_IDS,
    URL_RE,
)

SCRIPT_DIR = PROJECT_DIR
DEFAULT_SITES_FILE = str(PROJECT_DIR / "sites.json")


def normalized_site_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"网址必须是完整 http/https URL：{url}")
    scheme = parsed.scheme.lower()
    host = parsed.hostname.lower()
    port = parsed.port
    if port and not ((scheme == "https" and port == 443) or (scheme == "http" and port == 80)):
        host = f"{host}:{port}"
    return urlunsplit((scheme, host, parsed.path or "/", parsed.query, parsed.fragment))


def parse_pick(words: list[str]) -> tuple[str, list[str]]:
    pick = "all"
    kept: list[str] = []
    for word in words:
        lowered = word.lower()
        if word in {"上", "顶部", "上面"} or lowered in {"top", "first"}:
            pick = "top"
        elif word in {"下", "尾部", "底部", "下面", "最下面"} or lowered in {"bottom", "last"}:
            pick = "bottom"
        else:
            kept.append(word)
    return pick, kept


def parse_site_lines(lines: list[str], source: str) -> list[Site]:
    sites: list[Site] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    for line_no, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        match = URL_RE.search(line)
        if not match:
            raise ValueError(f"{source}:{line_no} 没有找到网址")

        url = match.group(0).rstrip("，,;；")
        before = line[: match.start()].strip()
        after = line[match.end() :].strip()
        words = (before + " " + after).split()
        pick, name_words = parse_pick(words)
        name = " ".join(name_words).strip()
        if not name:
            parsed = urlparse(url)
            name = parsed.netloc or f"第{line_no}行"
        if pick not in {"top", "bottom"}:
            raise ValueError(
                f"{source}:{line_no} 缺少或无法识别 pick，只允许 top/bottom/顶部/尾部/上/下"
            )
        if name in seen_names:
            raise ValueError(f"{source}:{line_no} 网站名称重复：{name}")
        normalized_url = normalized_site_url(url)
        if normalized_url in seen_urls:
            raise ValueError(f"{source}:{line_no} 网站 URL 重复：{url}")
        seen_names.add(name)
        seen_urls.add(normalized_url)
        sites.append(Site(name=name, url=url, pick=pick, line_no=line_no))

    if not sites:
        raise ValueError(f"网站列表为空：{source}")
    return sites


def pick_to_text(pick: str) -> str:
    if pick == "top":
        return "顶部"
    if pick == "bottom":
        return "下"
    return ""


def parse_json_sites(text: str, source: str) -> list[Site]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{source} JSON 格式错误：{exc}") from exc

    if not isinstance(data, list):
        raise ValueError(f"{source} 顶层必须是数组")

    sites: list[Site] = []
    seen_names: set[str] = set()
    seen_urls: set[str] = set()
    seen_rule_identities: set[str] = set()
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"{source}:{index} 必须是对象")
        name = str(item.get("name") or item.get("网站名称") or "").strip()
        url = str(item.get("url") or item.get("网址") or "").strip()
        raw_pick = str(item.get("region") or item.get("pick") or item.get("位置") or "").strip()
        if not name or not url:
            raise ValueError(f"{source}:{index} 缺少 name/url")
        if not raw_pick:
            raise ValueError(f"{source}:{index} 缺少 pick/region")
        pick, remaining = parse_pick([raw_pick])
        if pick not in {"top", "bottom"} or remaining:
            raise ValueError(f"{source}:{index} pick 只能是 top/bottom/顶部/尾部")

        parser_id = str(
            item.get("parser")
            or item.get("parser_id")
            or ""
        ).strip()
        if not parser_id:
            raise ValueError(f"{source}:{index} 缺少 parser，正式站点必须声明专属解析器")
        if parser_id not in SUPPORTED_PARSER_IDS:
            raise ValueError(f"{source}:{index} 解析器未注册：{parser_id}")
        special_parser_urls = {
            "caiyuntong_macau": CAIYUNTONG_URL,
            "guangdong_baer_left_half_head": GUANGDONG_BAER_URL,
            "sewai_taoyuan": SEWAI_TAOYUAN_URL,
            "shenzhen_futan_half_head": SHENZHEN_FUTAN_URL,
            "wuzhuanxingyi_embedded": WUZHUANXINGYI_URL,
        }
        expected_url = special_parser_urls.get(parser_id)
        if expected_url is not None and url != expected_url:
            raise ValueError(f"{source}:{index} 解析器与专属 URL 不匹配：{parser_id}")

        raw_anchors = item.get("anchors", item.get("anchor", ()))
        if isinstance(raw_anchors, str):
            anchors = tuple(
                part.strip() for part in re.split(r"[,，、]+", raw_anchors) if part.strip()
            )
        elif isinstance(raw_anchors, list):
            anchors = tuple(str(part).strip() for part in raw_anchors if str(part).strip())
        else:
            anchors = ()
        if not anchors:
            raise ValueError(f"{source}:{index} 缺少 anchors，正式站点必须声明栏目锚点")

        fetch_url = str(item.get("fetch_url") or "").strip()
        if fetch_url:
            normalized_site_url(fetch_url)
        entry_mode = str(
            item.get("entry_mode") or "direct"
        ).strip().lower()
        if entry_mode not in {"direct", "issue_link", "reference_issue_link"}:
            raise ValueError(
                f"{source}:{index} entry_mode 只能是 direct/issue_link/reference_issue_link"
            )
        if entry_mode == "issue_link" and not fetch_url:
            raise ValueError(f"{source}:{index} issue_link 站点必须显式声明 fetch_url")

        if name in seen_names:
            raise ValueError(f"{source}:{index} 网站名称重复：{name}")
        normalized_url = normalized_site_url(url)
        if normalized_url in seen_urls:
            raise ValueError(f"{source}:{index} 网站 URL 重复：{url}")
        site = Site(
            name,
            url,
            pick,
            index,
            parser_id,
            anchors,
            fetch_url,
            entry_mode,
        )
        if site.rule_identity in seen_rule_identities:
            raise ValueError(f"{source}:{index} 专属解析身份重复：{site.rule_identity}")
        seen_names.add(name)
        seen_urls.add(normalized_url)
        seen_rule_identities.add(site.rule_identity)
        sites.append(site)
    if not sites:
        raise ValueError(f"网站列表为空：{source}")
    return sites


def write_default_sites_json(path: Path) -> None:
    raise RuntimeError(f"禁止自动生成默认 sites.json，必须使用人工维护的正式配置：{path}")


def read_sites(path: Path, *, script_dir: Path = SCRIPT_DIR) -> list[Site]:
    if not path.is_absolute() and not path.exists():
        script_side_path = script_dir / path
        if script_side_path.exists():
            path = script_side_path

    if path.exists():
        if path.suffix.lower() != ".json":
            raise ValueError(f"网站列表必须是 JSON 文件：{path}")
        text = path.read_text(encoding="utf-8-sig")
        return parse_json_sites(text, str(path))

    raise FileNotFoundError(f"找不到网站列表：{path}")


def reject_new_sites_with_existing_names(existing_sites: list[Site], new_sites: list[Site]) -> None:
    existing_names = {site.name for site in existing_sites}
    conflicts = [site.name for site in new_sites if site.name in existing_names]
    if conflicts:
        names = "、".join(dict.fromkeys(conflicts))
        raise ValueError(f"新增网站名称与已有站点同名，直接拒收：{names}")


def read_failed_sites(path: Path, all_sites: list[Site]) -> list[Site]:
    if not path.exists():
        raise FileNotFoundError(f"找不到失败结果文件：{path}")

    rows = path.read_text(encoding="utf-8-sig").splitlines()
    wanted_names: set[str] = set()
    wanted_urls: set[str] = set()
    for line in rows[1:]:
        if not line.strip() or line.startswith("无失败"):
            continue
        parts = line.split("\t")
        if parts:
            wanted_names.add(parts[0].strip())
        for match in URL_RE.finditer(line):
            wanted_urls.add(match.group(0).rstrip("，,;；"))

    selected = [
        site for site in all_sites if site.name in wanted_names or site.url in wanted_urls
    ]
    if not selected:
        raise ValueError(f"失败结果里没有匹配到可重跑的网站：{path}")
    return selected
