# -*- coding: utf-8 -*-
import sys
from pathlib import Path

from ..config.issues import parse_issue_range
from ..config.sites import read_sites
from ..domain.models import Site
from ..fetching.policy import run_transport_scope
from ..outputs.formatting import spaced_failure_lines
from ..outputs.transaction import write_transaction
from ..paths import FAILURE_RESULT_DIR, PROJECT_DIR, RESULT_DIR
from .single_period import main as run_single_period

SCRIPT_DIR = PROJECT_DIR


def parse_periods(value: str) -> list[int]:
    periods, _width, _label = parse_issue_range(value)
    return periods


def output_label(periods: list[int]) -> str:
    ordered = sorted(periods)
    if len(ordered) > 1 and ordered == list(range(ordered[0], ordered[-1] + 1)):
        return f"{ordered[0]}-{ordered[-1]}"
    return "_".join(str(period) for period in periods)


def read_success_names(path: Path) -> set[str]:
    if not path.exists():
        return set()
    names: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("="):
            break
        parts = line.split("\t")
        if len(parts) >= 2:
            names.add(parts[1].strip())
    return names


def read_failure_reasons(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    reasons: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
        if not raw_line.strip():
            continue
        parts = raw_line.split("\t")
        if len(parts) >= 4:
            name, category, reason, _url = parts[:4]
            reasons[name] = f"{category}：{reason}"
    return reasons


def run_period(period: int) -> None:
    print(f"\n===== 开始抓取 {period}期 =====", flush=True)
    exit_code = run_single_period([str(period), "--multi-mode"])
    if exit_code:
        raise RuntimeError(f"{period}期正式抓取退出码：{exit_code}")


def load_sites() -> list[Site]:
    return read_sites(SCRIPT_DIR / "sites.json")


def write_summary(periods: list[int]) -> Path:
    sites = load_sites()
    success_by_period: dict[int, set[str]] = {}
    failure_by_period: dict[int, dict[str, str]] = {}
    for period in periods:
        success_path = RESULT_DIR / f"{period}期-半头.txt"
        fail_path = FAILURE_RESULT_DIR / f"{period}期-半头-失败.txt"
        success_by_period[period] = read_success_names(success_path)
        failure_by_period[period] = read_failure_reasons(fail_path)

    lines = [
        f"多期汇总失败报告：{', '.join(f'{period}期' for period in periods)}",
        "判定规则：任意一期成功=通过；全部期数失败=失败",
        "说明：本报告只列全部失败的目录",
        "",
    ]

    headers = ["网站名称", "结果"]
    headers.extend(f"{period}期失败原因" for period in periods)
    headers.append("网址")
    summary_rows = ["\t".join(headers)]

    failed_count = 0
    for site in sites:
        has_success = any(site.name in success_by_period[period] for period in periods)
        if has_success:
            continue
        failed_count += 1
        row = [site.name, "全部失败"]
        for period in periods:
            reason = failure_by_period[period].get(
                site.name,
                "未生成失败原因（该期未出现在成功/失败文件）",
            )
            row.append(reason)
        row.append(site.url)
        summary_rows.append("\t".join(row))

    if failed_count == 0:
        summary_rows.append("无\t全部通过\t" + "\t".join("无" for _ in periods) + "\t")

    lines.extend(spaced_failure_lines(summary_rows))

    FAILURE_RESULT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = FAILURE_RESULT_DIR / f"{output_label(periods)}期-半头-多期汇总失败.txt"
    write_transaction({summary_path: ("\n".join(lines) + "\n").encode("utf-8-sig")})
    print(f"\n多期汇总：总目录 {len(sites)}，全部失败 {failed_count}，通过 {len(sites) - failed_count}")
    print(f"多期汇总失败报告：{summary_path.resolve()}")
    return summary_path


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    try:
        periods = parse_periods(" ".join(args))
        with run_transport_scope():
            for period in periods:
                run_period(period)
        write_summary(periods)
        return 0
    except Exception as exc:
        print(f"多期抓取中断：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
