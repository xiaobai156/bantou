"""Read user input as Python data, never as a shell command."""
from bantou.application.single_period import main as crawl_main
from bantou.config.issues import parse_issue_range

def main() -> int:
    try:
        raw = input("请输入单期期数，例如 251：").strip()
        issues, _width, _label = parse_issue_range(raw)
        if len(issues) != 1:
            raise ValueError("这里只接受一期；多期使用多期入口")
    except (EOFError, ValueError) as exc:
        print(f"输入错误：{exc}")
        return 2
    return crawl_main([str(issues[0])])

if __name__ == "__main__":
    raise SystemExit(main())
