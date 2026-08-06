from pathlib import Path

from ..domain import Site
from .cli import build_parser, prompt_if_missing, resolve_inputs
from .issues import parse_issue_range
from .sites import (
    DEFAULT_SITES_FILE,
    SCRIPT_DIR as _DEFAULT_SCRIPT_DIR,
    normalized_site_url,
    parse_json_sites,
    parse_pick,
    parse_site_lines,
    pick_to_text,
    read_failed_sites,
    reject_new_sites_with_existing_names,
    write_default_sites_json,
)
from .sites import read_sites as _read_sites

SCRIPT_DIR = _DEFAULT_SCRIPT_DIR


def read_sites(path: Path) -> list[Site]:
    return _read_sites(path, script_dir=SCRIPT_DIR)


__all__ = [
    "DEFAULT_SITES_FILE",
    "SCRIPT_DIR",
    "Site",
    "build_parser",
    "normalized_site_url",
    "parse_issue_range",
    "parse_json_sites",
    "parse_pick",
    "parse_site_lines",
    "pick_to_text",
    "prompt_if_missing",
    "read_failed_sites",
    "read_sites",
    "reject_new_sites_with_existing_names",
    "resolve_inputs",
    "write_default_sites_json",
]
