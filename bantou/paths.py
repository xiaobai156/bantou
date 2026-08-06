# -*- coding: utf-8 -*-
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
RESULT_DIR = PROJECT_DIR.parent / "七类数据统一归纳"
FAILURE_RESULT_DIR = PROJECT_DIR.parent / "七类数据统一归纳失败"
DEFAULT_SITES_FILE = PROJECT_DIR / "sites.json"
DUPLICATE_BACKUP_FILE = PROJECT_DIR / "recent_10_cache.json"
