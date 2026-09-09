"""Safe interactive multi-period launcher."""
from bantou.application.multi_period import main as crawl_main
from bantou.config.issues import parse_issue_range

def main() -> int:
    try:
        raw = input("请输入期数，例如 249 250 251：").strip()
        issues, _width, _label = parse_issue_range(raw)
    except (EOFError, ValueError) as exc:
        print(f"输入错误：{exc}")
        return 2
    return crawl_main([str(issue) for issue in issues])

if __name__ == "__main__":
    raise SystemExit(main())
