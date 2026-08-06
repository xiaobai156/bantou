from dataclasses import dataclass


@dataclass(frozen=True)
class Site:
    name: str
    url: str
    pick: str
    line_no: int
    parser_id: str = ""
    anchors: tuple[str, ...] = ()
    fetch_url: str = ""
    entry_mode: str = "direct"

    @property
    def rule_identity(self) -> str:
        return f"{self.name}|{self.url}|{self.pick}|{self.parser_id}"


class SourceDocument(str):
    """A text document that keeps the exact source boundary used for parsing."""

    def __new__(
        cls,
        text: str,
        *,
        source_url: str = "",
        source_kind: str = "page",
        record_id: str = "",
        record_path: str = "",
        route_type: str = "",
        url_record_id: str = "",
        api_url: str = "",
        title: str = "",
        author: str = "",
        position_offset: int = 0,
        container_id: str = "",
        document_authority: str = "",
        block_start: int = 0,
        block_end: int = 0,
        table_column: str = "",
    ):
        value = super().__new__(cls, text)
        value.source_url = source_url
        value.source_kind = source_kind
        value.record_id = record_id
        value.record_path = record_path
        value.route_type = route_type
        value.url_record_id = url_record_id
        value.api_url = api_url
        value.title = title
        value.author = author
        value.position_offset = position_offset
        value.container_id = container_id
        value.document_authority = document_authority
        value.block_start = block_start
        value.block_end = block_end
        value.table_column = table_column
        return value


@dataclass(frozen=True)
class Match:
    issue: int
    issue_text: str
    value: str
    snippet: str
    order: int
    document_order: int = 0
    position: int = 0
    source_url: str = ""
    source_kind: str = "page"
    record_id: str = ""
    record_path: str = ""
    route_type: str = ""
    url_record_id: str = ""
    api_url: str = ""
    title: str = ""
    author: str = ""
    anchor_text: str = ""
    anchor_position: int = -1
    block_id: str = ""
    block_start: int = 0
    block_end: int = 0
    container_id: str = ""
    table_column: str = ""
    document_authority: str = ""
    rule_id: str = ""


@dataclass(frozen=True)
class PreviousInfo:
    issue: int
    value: str
    open_info: str
    status: str
    rank_ok: bool
    reason: str


@dataclass(frozen=True)
class SiteResult:
    index: int
    site: Site
    matches: list[Match]
    error: str | None = None
    script_error_count: int = 0
    miss_reason: str | None = None
    debug_sample: str = ""
    rejection_evidence: tuple[str, ...] = ()
    direction_evidence: tuple[Match, ...] = ()
