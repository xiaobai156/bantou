from __future__ import annotations

import os
import subprocess


BASE_SHA = os.environ["BASE_SHA"]
RESULT_BRANCH = os.environ["RESULT_BRANCH"]
FILES = [
    "bantou/parsers/segments.py",
    "bantou/parsers/matching.py",
    "bantou/parsers/dedicated.py",
    "bantou/text.py",
    "bantou/documents/content.py",
    "bantou/application/site_crawl.py",
    "bantou/outputs/formatting.py",
    "bantou/application/single_period.py",
    "bantou/application/multi_period.py",
    "bantou/fetching/browser_process.py",
    "bantou/documents/collection.py",
    "bantou/fetching/policy.py",
    "bantou/config/cli.py",
    "bantou/fetching/transport.py",
    "bantou/cache/validation.py",
    "bantou/application/site_validation.py",
    "constraints.txt",
    "tests/test_audit_repairs.py",
    "tests/test_audit_round3.py",
    "docs/audit-repair-round3-20260909.md",
]


def run(*args: str, input_text: str | None = None) -> str:
    completed = subprocess.run(
        args,
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    return completed.stdout.strip()


run("git", "config", "user.name", "github-actions[bot]")
run(
    "git",
    "config",
    "user.email",
    "41898282+github-actions[bot]@users.noreply.github.com",
)
run("git", "read-tree", BASE_SHA)
run("git", "add", "--", *FILES)
run("git", "diff", "--cached", "--check")
run("git", "diff", "--cached", "--stat")
tree = run("git", "write-tree").splitlines()[-1]
message = (
    "fix: close remaining audited accuracy and isolation gaps\n\n"
    "Windows Python 3.10/3.11 regressions and local Chromium smoke passed.\n"
    "Production sites, cache and result data were not changed.\n"
)
commit = run(
    "git", "commit-tree", tree, "-p", BASE_SHA, input_text=message
).splitlines()[-1]
print(f"CANDIDATE_SHA={commit}")
run(
    "git",
    "push",
    "--force",
    "origin",
    f"{commit}:refs/heads/{RESULT_BRANCH}",
)
