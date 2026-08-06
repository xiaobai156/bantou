# -*- coding: utf-8 -*-
import html
import re
from html.parser import HTMLParser


ANY_VALUE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*头\s*(单|双)")
VALUE_RE = re.compile(r"(?<!\d)([0-4])\s*头\s*(单|双)")
ISSUE_RE = re.compile(r"(?<!\d)(\d{1,4})\s*期")
SOURCE_ISSUE_TOKEN_RE = re.compile(
    r"(?<![0-9０-９])([0-9０-９]{1,4})(?:[\s\u00a0\u3000]|&nbsp;|&#160;)*期"
)
TABLE_ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.I | re.S)
TABLE_RE = re.compile(r"<table\b[^>]*>(.*?)</table>", re.I | re.S)
TABLE_CELL_RE = re.compile(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", re.I | re.S)
FULLWIDTH_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
FULLWIDTH_DIGIT_BY_ASCII = dict(zip("0123456789", "０１２３４５６７８９"))
CHAR_TRANS = str.maketrans(
    {
        "【": "[",
        "】": "]",
        "［": "[",
        "］": "]",
        "（": "(",
        "）": ")",
        "：": ":",
        "　": " ",
        "\xa0": " ",
        "頭": "头",
        "單": "单",
        "雙": "双",
    }
)
BLOCK_TAGS = {
    "address", "article", "aside", "blockquote", "br", "caption", "div", "footer",
    "h1", "h2", "h3", "h4", "h5", "h6", "header", "li", "p", "section", "table",
    "tbody", "td", "tfoot", "th", "thead", "tr", "ul", "ol",
}
VOID_HTML_TAGS = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
}


class PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


class RenderedContainerParser(HTMLParser):
    TARGET_CLASSES = {
        "content",
        "detail_info_forum2_item",
        "topic-content",
        "swiper-slide",
        "dz_content08",
    }
    AUTHOR_CLASSES = {"author", "topic-author"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.active: list[tuple[int, str, list[str], str, int]] = []
        self.active_authors: list[tuple[int, list[str]]] = []
        self.blocks: dict[str, list[str]] = {}
        self.block_author_contexts: dict[str, list[str]] = {}
        self.block_spans: dict[str, list[tuple[int, int]]] = {}
        self.page_parts: list[str] = []
        self.last_author = ""

    def page_text(self) -> str:
        return "".join(self.page_parts)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() in BLOCK_TAGS:
            for _start_depth, _class_name, parts, _author, _page_start in self.active:
                parts.append("\n")
            self.page_parts.append("\n")
        class_names = set(str(dict(attrs).get("class") or "").split())
        if class_names & self.AUTHOR_CLASSES:
            self.active_authors.append((self.depth, []))
        for class_name in class_names & self.TARGET_CLASSES:
            self.active.append(
                (self.depth, class_name, [], self.last_author, len(self.page_text()))
            )
        if tag.lower() not in VOID_HTML_TAGS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in VOID_HTML_TAGS:
            return
        self.depth -= 1
        if tag.lower() in BLOCK_TAGS:
            for _start_depth, _class_name, parts, _author, _page_start in self.active:
                parts.append("\n")
            self.page_parts.append("\n")
        finished = [item for item in self.active if item[0] == self.depth]
        if finished:
            self.active = [item for item in self.active if item[0] != self.depth]
            page_end = len(self.page_text())
            for _start_depth, class_name, parts, author_context, page_start in finished:
                self.blocks.setdefault(class_name, []).append("".join(parts))
                self.block_author_contexts.setdefault(class_name, []).append(author_context)
                self.block_spans.setdefault(class_name, []).append((page_start, page_end))
        finished_authors = [item for item in self.active_authors if item[0] == self.depth]
        if finished_authors:
            self.active_authors = [item for item in self.active_authors if item[0] != self.depth]
            for _start_depth, parts in finished_authors:
                self.last_author = "".join(parts)

    def handle_data(self, data: str) -> None:
        if data:
            self.page_parts.append(data)
            for _start_depth, _class_name, parts, _author, _page_start in self.active:
                parts.append(data)
            for _start_depth, parts in self.active_authors:
                parts.append(data)


def normalize_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.translate(FULLWIDTH_DIGITS).translate(CHAR_TRANS)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n+ *", "\n", text)
    return text.strip()


def issue_token_positions(text: str, issue_text: str) -> list[int]:
    """Return exact source offsets for one issue token without normalizing it."""
    digits = "".join(
        f"[{digit}{FULLWIDTH_DIGIT_BY_ASCII[digit]}]" for digit in str(issue_text)
    )
    pattern = re.compile(
        rf"(?<![0-9０-９]){digits}(?:[\s\u00a0\u3000]|&nbsp;|&#160;)*期"
    )
    return [match.start() for match in pattern.finditer(text or "")]


def _inside_html_tag(text: str, position: int) -> bool:
    return text.rfind("<", 0, position) > text.rfind(">", 0, position)


def source_issue_token_positions(text: str, *, browser_text: bool = False) -> list[int]:
    positions: list[int] = []
    for match in SOURCE_ISSUE_TOKEN_RE.finditer(text or ""):
        if browser_text or not _inside_html_tag(text, match.start()):
            positions.append(match.start())
    return positions


def original_issue_position(
    source_text: str,
    searched_text: str,
    issue_text: str,
    searched_position: int,
    required_value: str | None = None,
) -> int | None:
    """Map a parsed issue token back to its unique source-document offset.

    Parsing may inspect plain text or an extracted table, but the cache must
    retain a position from the original source document rather than a parser
    candidate ordinal.  When a value is supplied, an occurrence must also
    contain that value before the next same-issue token; this excludes IDs and
    attributes that merely contain the same issue number.
    """
    is_browser_text = getattr(source_text, "source_kind", "") == "browser-text"
    searched_positions = issue_token_positions(searched_text, issue_text)
    source_positions = [
        position
        for position in issue_token_positions(source_text, issue_text)
        if is_browser_text or not _inside_html_tag(source_text, position)
    ]
    if required_value:
        compact_value = re.sub(r"\s+", "", normalize_text(required_value))

        def positions_with_value(
            text: str,
            positions: list[int],
            *,
            plain_text: bool = False,
        ) -> list[int]:
            matches: list[int] = []
            for index, position in enumerate(positions):
                end = positions[index + 1] if index + 1 < len(positions) else len(text)
                # Browser-extracted text can legitimately include literal markup
                # fragments. Treating it as HTML again can hide all later content.
                segment = text[position:end] if plain_text else html_to_text(text[position:end])
                compact_segment = re.sub(r"\s+", "", normalize_text(segment))
                if compact_value in compact_segment:
                    matches.append(position)
            return matches

        searched_positions = positions_with_value(
            searched_text, searched_positions, plain_text=is_browser_text
        )
        source_positions = positions_with_value(
            source_text, source_positions, plain_text=is_browser_text
        )
    try:
        occurrence = searched_positions.index(searched_position)
    except ValueError:
        return None

    if occurrence >= len(source_positions):
        return None
    return source_positions[occurrence]


def compact_line(text: str, limit: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", normalize_text(text))
    if len(normalized) > limit:
        return normalized[: limit - 3] + "..."
    return normalized


def valid_half_head_no(value: str | int) -> bool:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return False
    return 0 <= number <= 4


def normalize_half_head_value(head_no: str | int, parity: str) -> str | None:
    if not valid_half_head_no(head_no):
        return None
    return f"{int(head_no)}头{parity}"


def normalize_target(text: str) -> str:
    normalized = normalize_text(text)
    match = ANY_VALUE_RE.search(normalized)
    if not match:
        raise ValueError("目标格式不对，例子：2头双、0头单")
    if not valid_half_head_no(match.group(1)):
        raise ValueError("半头数字只能是 0-4，例子：2头双、0头单")
    return f"{int(match.group(1))}头{match.group(2)}"


def html_to_text(document: str) -> str:
    parser = PlainTextParser()
    try:
        parser.feed(document)
        parser.close()
    except Exception:
        return normalize_text(re.sub(r"<[^>]+>", " ", document))
    return normalize_text(parser.text())


def extract_half_head_table_texts(document: str) -> list[str]:
    extracted: list[str] = []
    seen: set[tuple[str, str]] = set()
    table_blocks = TABLE_RE.findall(document or "")
    row_groups = [TABLE_ROW_RE.findall(table_html) for table_html in table_blocks]
    if not row_groups:
        row_groups = [TABLE_ROW_RE.findall(document or "")]

    for rows in row_groups:
        half_head_indexes: list[int] = []
        for row_html in rows:
            cells_html = TABLE_CELL_RE.findall(row_html)
            if not cells_html:
                continue

            cells = [
                normalize_text(re.sub(r"<[^>]+>", " ", html.unescape(cell_html)))
                for cell_html in cells_html
            ]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            current_half_head_indexes = [
                index for index, cell in enumerate(cells) if "半头" in re.sub(r"\s+", "", cell)
            ]
            issue_cell = next((cell for cell in cells if ISSUE_RE.search(cell)), "")
            if current_half_head_indexes and not issue_cell:
                half_head_indexes = current_half_head_indexes
                continue
            if current_half_head_indexes:
                half_head_indexes = current_half_head_indexes

            if not half_head_indexes or not issue_cell:
                continue

            issue_match = ISSUE_RE.search(issue_cell)
            assert issue_match is not None

            for index in half_head_indexes:
                if index >= len(cells):
                    continue
                value_match = VALUE_RE.search(cells[index])
                if not value_match:
                    continue
                value = f"{int(value_match.group(1))}头{value_match.group(2)}"
                open_cell = next(
                    (
                        re.sub(r"\s+", "", cell)
                        for cell in cells
                        if "期" not in cell
                        and re.search(r"[鼠牛虎兔龙蛇马羊猴鸡狗猪？?]?\s*\d{2,4}\s*[准对错中√×xX]?", cell)
                        and (
                            "开" in cell
                            or any(marker in cell for marker in ("准", "对", "错", "中", "√", "×", "x", "X"))
                            or any(animal in cell for animal in "鼠牛虎兔龙蛇马羊猴鸡狗猪")
                        )
                    ),
                    "",
                )
                key = (issue_match.group(1), value)
                if key not in seen:
                    seen.add(key)
                    suffix = f" 开{open_cell}" if open_cell else ""
                    extracted.append(f"{issue_match.group(1)}期 杀半头 {value}{suffix}")

            if half_head_indexes:
                continue

    if extracted:
        return extracted

    for table_html in table_blocks or [document or ""]:
        extracted.extend(extract_table_window_texts(table_html, seen))

    return extracted


def extract_table_window_texts(table_html: str, seen: set[tuple[str, str]]) -> list[str]:
    cells_html = TABLE_CELL_RE.findall(table_html or "")
    cells = [
        normalize_text(re.sub(r"<[^>]+>", " ", html.unescape(cell_html)))
        for cell_html in cells_html
    ]
    cells = [cell for cell in cells if cell]
    extracted: list[str] = []
    for index in range(0, max(0, len(cells) - 4)):
        window = cells[index : index + 5]
        issue_match = ISSUE_RE.search(window[0])
        if not issue_match:
            continue
        value_matches = [VALUE_RE.search(cell) for cell in window]
        value_matches = [match for match in value_matches if match]
        if len(value_matches) != 1:
            continue
        has_union_cell = any("合" in cell for cell in window)
        has_open_cell = any(
            "期" not in cell
            and re.search(r"[鼠牛虎兔龙蛇马羊猴鸡狗猪]?\s*\d{2,4}\s*[准对错中√×xX]?", cell)
            for cell in window
        )
        if not (has_union_cell and has_open_cell):
            continue
        value_match = value_matches[0]
        value = f"{int(value_match.group(1))}头{value_match.group(2)}"
        open_cell = next(
            (
                re.sub(r"\s+", "", cell)
                for cell in window
                if "期" not in cell
                and re.search(r"[鼠牛虎兔龙蛇马羊猴鸡狗猪？?]?\s*\d{2,4}\s*[准对错中√×xX]?", cell)
                and (
                    "开" in cell
                    or any(marker in cell for marker in ("准", "对", "错", "中", "√", "×", "x", "X"))
                    or any(animal in cell for animal in "鼠牛虎兔龙蛇马羊猴鸡狗猪")
                )
            ),
            "",
        )
        key = (issue_match.group(1), value)
        if key not in seen:
            seen.add(key)
            suffix = f" 开{open_cell}" if open_cell else ""
            extracted.append(f"{issue_match.group(1)}期 杀半头 {value}{suffix}")
    return extracted
