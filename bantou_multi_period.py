from bantou.application.multi_period import (
    load_sites,
    main,
    output_label,
    parse_periods,
    read_failure_reasons,
    read_success_names,
    run_period,
    write_summary,
)

__all__ = [name for name in globals() if not name.startswith("_")]

if __name__ == "__main__":
    raise SystemExit(main())
