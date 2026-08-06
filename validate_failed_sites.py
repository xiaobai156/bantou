from bantou.application.site_validation import (
    build_parser,
    main,
    print_result,
    select_sites,
)

__all__ = [name for name in globals() if not name.startswith("_")]

if __name__ == "__main__":
    raise SystemExit(main())
