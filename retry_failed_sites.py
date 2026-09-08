"""Read the retry period as data, never as a shell command."""

import re

from bantou.application.single_period import main as crawl_main


def main() -> int:
    try:
        issue = input("Input one period to retry failed sites, for example 251: ")
    except EOFError:
        print("Period is required.")
        return 2
    if re.fullmatch(r"[0-9]+", issue) is None:
        print("Period must contain digits only.")
        return 2
    return crawl_main([issue, "--retry-fail", "--write-backup", "--workers", "1"])


if __name__ == "__main__":
    raise SystemExit(main())
