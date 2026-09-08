"""Offline regression check: python -B check_retry_input.py."""

from unittest.mock import patch

import retry_failed_sites


def main():
    for value in ("251 & echo P1_REPRO", '251" & rem', "251|echo P1_REPRO", "", "251-252", "２５１"):
        with patch("builtins.input", return_value=value), patch.object(retry_failed_sites, "crawl_main") as crawl:
            assert retry_failed_sites.main() == 2, value
            crawl.assert_not_called()
    with patch("builtins.input", return_value="251"), patch.object(retry_failed_sites, "crawl_main", return_value=0) as crawl:
        assert retry_failed_sites.main() == 0
        crawl.assert_called_once_with(["251", "--retry-fail", "--write-backup", "--workers", "1"])
    print("Retry input checks passed; no network requests made.")


if __name__ == "__main__":
    main()
