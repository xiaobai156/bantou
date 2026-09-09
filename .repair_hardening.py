from __future__ import annotations

from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one hardening context, found {count}")
    write(path, text.replace(old, new, 1))


def append_once(path: str, marker: str, addition: str) -> None:
    text = read(path)
    if marker in text:
        raise RuntimeError(f"{path}: hardening test marker already present")
    write(path, text.rstrip() + "\n\n" + addition.strip() + "\n")


replace_once(
    "bantou/text.py",
    '''def _mask_ignored_html_blocks(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        return "".join("\\n" if char == "\\n" else " " for char in match.group(0))

    return _IGNORED_HTML_BLOCK_RE.sub(mask, text or "")


class PlainTextParser''',
    '''def _mask_ignored_html_blocks(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        return "".join("\\n" if char == "\\n" else " " for char in match.group(0))

    return _IGNORED_HTML_BLOCK_RE.sub(mask, text or "")


def source_text_without_hidden_html(text: str) -> str:
    """Mask hidden HTML blocks while preserving every source offset."""
    return _mask_ignored_html_blocks(text)


class PlainTextParser''',
)

replace_once(
    "bantou/parsers/matching.py",
    '''    source_issue_token_positions,
)
''',
    '''    source_issue_token_positions,
    source_text_without_hidden_html,
)
''',
)
replace_once(
    "bantou/parsers/matching.py",
    '''    raw_block = str(document)[block_start:block_end]
''',
    '''    raw_block = source_text_without_hidden_html(
        str(document)[block_start:block_end]
    )
''',
)

replace_once(
    "bantou/parsers/dedicated.py",
    '''    normalize_text,
)
''',
    '''    normalize_text,
    source_text_without_hidden_html,
)
''',
)
replace_once(
    "bantou/parsers/dedicated.py",
    '''        text = str(document)
        for card_match in WUZHUANXINGYI_CARD_RE.finditer(text):
''',
    '''        text = source_text_without_hidden_html(str(document))
        for card_match in WUZHUANXINGYI_CARD_RE.finditer(text):
''',
)
replace_once(
    "bantou/parsers/dedicated.py",
    '''        text = str(document)
        if "世外桃源" not in text or "绝杀半头" not in text:
''',
    '''        text = source_text_without_hidden_html(str(document))
        if "世外桃源" not in text or "绝杀半头" not in text:
''',
)
replace_once(
    "bantou/parsers/dedicated.py",
    '''        local_matches = caiyuntong_macau_matches_from_joined(document, wanted_issues)
''',
    '''        local_matches = caiyuntong_macau_matches_from_joined(
            source_text_without_hidden_html(str(document)), wanted_issues
        )
''',
)
replace_once(
    "bantou/parsers/dedicated.py",
    '''        local_matches = guangdong_baer_left_half_head_matches_from_joined(
            document, wanted_issues
        )
''',
    '''        local_matches = guangdong_baer_left_half_head_matches_from_joined(
            source_text_without_hidden_html(str(document)), wanted_issues
        )
''',
)
replace_once(
    "bantou/parsers/dedicated.py",
    '''        text = str(document)
        target_titles = [
''',
    '''        text = source_text_without_hidden_html(str(document))
        target_titles = [
''',
)

replace_once(
    "bantou/application/single_period.py",
    '''    issue_text = f"{issues_label}期"
    existing_success = read_success_data_strict(
        success_path, issue_text, configured_sites
    )
''',
    '''    issue_text = f"{issues_label}期"
    try:
        target_issue = int(issues_label)
    except ValueError as exc:
        raise ValueError("失败重抓期数标签无效") from exc
    # Revalidate the on-disk failure file under the formal write lock. It may
    # have changed while network requests were running.
    validated_failed_sites = read_failed_sites(
        fail_path, configured_sites, issue=target_issue
    )
    success_existed = success_path.exists()
    existing_success = read_success_data_strict(
        success_path, issue_text, configured_sites
    )
    existing_fail_entries = read_fail_entries(fail_path)
    if not success_existed:
        configured_identities = {
            (site.name, _failure_url_identity(site.url)) for site in configured_sites
        }
        failed_identities = {
            (site.name, _failure_url_identity(site.url))
            for site in validated_failed_sites
        }
        if failed_identities != configured_identities:
            raise ValueError(
                "成功文件不存在，且失败文件未覆盖全部正式站点；拒绝猜测原成功结果"
            )
''',
)
replace_once(
    "bantou/application/single_period.py",
    '''        for name, category, reason, url in read_fail_entries(fail_path)
''',
    '''        for name, category, reason, url in existing_fail_entries
''',
)

replace_once(
    "bantou/fetching/policy.py",
    '''        "--max-time",
        str(timeout),
        "--write-out",
''',
    '''        "--max-time",
        str(timeout),
        "--max-filesize",
        str(MAX_BODY_BYTES),
        "--write-out",
''',
)

append_once(
    "tests/test_audit_round3.py",
    "test_hidden_script_anchor_after_visible_issue_is_ignored",
    r'''
def test_hidden_script_anchor_after_visible_issue_is_ignored(monkeypatch):
    html = (
        "<p>251期</p><script>const fake='半头';</script>"
        "<p>必杀半头 2头双 开00对</p>"
    )
    result = run_document(monkeypatch, html)
    assert result.matches
    assert result.matches[0].anchor_position == html.rindex("半头")


def test_retry_without_success_requires_all_sites_in_failure_file(tmp_path):
    bad = failure_file(tmp_path)
    configured = [site("A"), site("B", "https://example.test/b")]
    with pytest.raises(ValueError, match="未覆盖全部正式站点"):
        single_period._merge_retry_rows(
            "251",
            [],
            ["网站名称\t分类\t原因\t网址"],
            success_path=tmp_path / "251期-半头.txt",
            fail_path=bad,
            configured_sites=configured,
        )


def test_retry_merge_revalidates_changed_failure_identity(tmp_path):
    good = tmp_path / "251期-半头.txt"
    good.write_text(
        "2头双 A\n\n内容\t次数\t排名\n2头双\t1\t1\n",
        encoding="utf-8-sig",
    )
    bad = failure_file(
        tmp_path,
        text=(
            "网站名称\t分类\t原因\t网址\n"
            "B\t超时\t超时\thttps://example.test/a\n"
        ),
    )
    with pytest.raises(ValueError, match="成对匹配"):
        single_period._merge_retry_rows(
            "251",
            [],
            ["网站名称\t分类\t原因\t网址"],
            success_path=good,
            fail_path=bad,
            configured_sites=[site("A"), site("B", "https://example.test/b")],
        )


def test_curl_command_enforces_download_size_limit():
    command = policy.curl_command("https://example.test/a", 2, True)
    index = command.index("--max-filesize")
    assert int(command[index + 1]) == policy.MAX_BODY_BYTES
''',
)

print("Applied final hidden-source, retry-TOCTOU and curl-size hardening.")
