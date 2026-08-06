from bantou.application.duplicate_detection import (
    DuplicateReport,
    DuplicateRun,
    build_parser,
    cache_record_signature,
    evaluate_cache,
    find_consecutive_matches,
    format_report,
    main,
    read_cache,
)

__all__ = [name for name in globals() if not name.startswith("_")]

if __name__ == "__main__":
    raise SystemExit(main())
