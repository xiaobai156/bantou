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
FULLWIDTH_DIGIT_BY_ASCII = dict(zip("0123456789", "０１２３４５６７８９", strict=True))
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
IGNORED_HTML_TAGS = {"script", "style", "template", "noscript"}
_IGNORED_HTML_BLOCK_RE = re.compile(
    r"<(?P<tag>script|style|template|noscript)\b[^>]*>[\s\S]*?(?:</(?P=tag)\s*>|\Z)",
    re.I,
)


def _ignored_html_ranges(text: str) -> tuple[tuple[int, int], ...]:
    return tuple((match.start(), match.end()) for match in _IGNORED_HTML_BLOCK_RE.finditer(text or ""))


def _position_in_ranges(position: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(start <= position < end for start, end in ranges)


def _mask_ignored_html_blocks(text: str) -> str:
    def mask(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return _IGNORED_HTML_BLOCK_RE.sub(mask, text or "")


def source_text_without_hidden_html(text: str) -> str:
    """Mask hidden HTML blocks while preserving every source offset."""
    return _mask_ignored_html_blocks(text)


class PlainTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self.ignored_depth:
            if tag not in VOID_HTML_TAGS:
                self.ignored_depth += 1
            return
        if tag in IGNORED_HTML_TAGS:
            self.ignored_depth = 1
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.ignored_depth:
            if tag not in VOID_HTML_TAGS:
                self.ignored_depth -= 1
            return
        if tag in BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth and data:
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
        self.ignored_depth = 0

    def page_text(self) -> str:
        return "".join(self.page_parts)

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if self.ignored_depth:
            if tag not in VOID_HTML_TAGS:
                self.depth += 1
                self.ignored_depth += 1
            return
        if tag in IGNORED_HTML_TAGS:
            self.depth += 1
            self.ignored_depth = 1
            return
        if tag in BLOCK_TAGS:
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
        if tag not in VOID_HTML_TAGS:
            self.depth += 1

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in VOID_HTML_TAGS:
            return
        self.depth -= 1
        if self.ignored_depth:
            self.ignored_depth -= 1
            return
        if tag in BLOCK_TAGS:
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
        if self.ignored_depth:
            return
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
    ignored_ranges = () if browser_text else _ignored_html_ranges(text)
    for match in SOURCE_ISSUE_TOKEN_RE.finditer(text or ""):
        if browser_text or (
            not _inside_html_tag(text, match.start())
            and not _position_in_ranges(match.start(), ignored_ranges)
        ):
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
    ignored_ranges = () if is_browser_text else _ignored_html_ranges(source_text)
    source_positions = [
        position
        for position in issue_token_positions(source_text, issue_text)
        if is_browser_text
        or (
            not _inside_html_tag(source_text, position)
            and not _position_in_ranges(position, ignored_ranges)
        )
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
    match = ANY_VALUE_RE.fullmatch(normalized)
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
        visible = _mask_ignored_html_blocks(document)
        return normalize_text(re.sub(r"<[^>]+>", " ", visible))
    return normalize_text(parser.text())



class TableSearchText(str):
    def __new__(cls, text, position, row_end, header_start, header_end):
        obj = super().__new__(cls, text)
        obj.source_position = position
        obj.source_row_end = row_end
        obj.source_header_start = header_start
        obj.source_header_end = header_end
        return obj


def extract_half_head_table_texts(document: str) -> list[str]:
    extracted = []
    seen = set()
    working_document = _mask_ignored_html_blocks(document or "")
    tables = list(TABLE_RE.finditer(working_document))
    groups = [(m.group(1), m.start(1)) for m in tables] or [(working_document, 0)]
    for table_html, table_offset in groups:
        if re.search(r"<table\b", table_html, re.I):
            continue  # Nested/merged layout needs its declared dedicated parser.
        header_indexes = []
        headers = {}
        for row in TABLE_ROW_RE.finditer(table_html):
            row_html = row.group(1)
            row_start = table_offset + row.start(1)
            row_end = table_offset + row.end(1)
            cells = list(TABLE_CELL_RE.finditer(row_html))
            texts = [normalize_text(html_to_text(cell.group(1))) for cell in cells]
            if not texts:
                continue
            if re.search(r"\b(?:colspan|rowspan)\s*=\s*[\"']?(?:[2-9]|[1-9][0-9])", row_html, re.I):
                header_indexes = []
                headers = {}
                continue  # Do not carry a prior column map across merged cells.
            issue_cells = [i for i, text in enumerate(texts) if ISSUE_RE.search(text)]
            current_headers = [i for i, text in enumerate(texts) if "半头" in re.sub(r"\s+", "", text)]
            if not issue_cells:
                if current_headers:
                    header_indexes = current_headers
                    headers = {i: (row_start + cells[i].start(1), row_start + cells[i].end(1)) for i in current_headers}
                elif re.search(r"<th\b", row_html, re.I) or not any(VALUE_RE.search(text) for text in texts):
                    header_indexes = []
                    headers = {}
                continue
            if len(issue_cells) != 1:
                continue
            issue_index = issue_cells[0]
            tokens = list(ISSUE_RE.finditer(texts[issue_index]))
            if len(tokens) != 1:
                continue
            token = tokens[0]
            raw_cell_start = row_start + cells[issue_index].start(1)
            raw_cell_end = row_start + cells[issue_index].end(1)
            positions = [p for p in issue_token_positions(working_document, token.group(1)) if raw_cell_start <= p < raw_cell_end]
            if len(positions) != 1:
                continue
            indexes = current_headers or header_indexes
            for index in indexes:
                if index >= len(cells):
                    continue
                if index in current_headers:
                    header_start, header_end = row_start + cells[index].start(1), row_start + cells[index].end(1)
                else:
                    header_start, header_end = headers[index]
                open_cell = next((text for text in texts if "期" not in text and re.search(r"开\s*[:：]?\s*[鼠牛虎兔龙蛇马羊猴鸡狗猪]?\s*[0-9]{2,4}", text)), "")
                if not open_cell:
                    continue
                for value_match in VALUE_RE.finditer(texts[index]):
                    value = f"{int(value_match.group(1))}头{value_match.group(2)}"
                    key = (positions[0], token.group(1), value, index)
                    if key in seen:
                        continue
                    seen.add(key)
                    extracted.append(TableSearchText(
                        f"{token.group(1)}期 杀半头 {value} {open_cell}",
                        positions[0], row_end, header_start, header_end,
                    ))
    return extracted


def extract_table_window_texts(table_html: str, seen: set[tuple[str, str]]) -> list[str]:
    cells_html = TABLE_CELL_RE.findall(table_html or "")
    cells = [
        normalize_text(re.sub(r"<[^>]+>", " ", html.unescape(cell_html)))
        for cell_html in cells_html
    ]
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
