import argparse

from ..text import VALUE_RE, normalize_text
from .sites import DEFAULT_SITES_FILE


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="抓取网站指定期数里实际写的半头内容，并分别输出成功/失败 txt。"
    )
    parser.add_argument(
        "pos_args",
        nargs="*",
        help="必填：120 或 120 sites.json",
    )
    parser.add_argument("-t", "--target", help="可选筛选目标，例如：2头双；不填就抓网站实际写的头")
    parser.add_argument("-i", "--issues", help="期数，例如：120 或 094-120")
    parser.add_argument("-s", "--sites", help="网站列表 JSON")
    parser.add_argument("--success-out", default="", help="成功结果 txt；不填则自动生成 N期-半头.txt")
    parser.add_argument("--fail-out", default="", help="失败结果 txt；不填则自动生成 N期-半头-失败.txt")
    parser.add_argument("--retry-fail", action="store_true", help="只重跑上次失败结果里的网站")
    parser.add_argument("--retry-fail-file", default="", help="指定要重跑的失败结果 txt；默认使用本期半头失败文件")
    parser.add_argument("--timeout", type=int, default=20, help="单个请求超时秒数")
    parser.add_argument("--site-timeout", type=int, default=60, help="单站总超时秒数，默认 60")
    parser.add_argument("--delay", type=float, default=0.0, help="每个网站之间暂停秒数，默认 0")
    parser.add_argument("--workers", type=int, default=10, help="并发线程数，默认 10")
    parser.add_argument("--retries", type=int, default=1, help="同一网址失败后的重试次数，默认 1")
    parser.add_argument(
        "--write-backup",
        action="store_true",
        help="单期结果完成后独立更新 recent_10_cache.json；缓存不参与本次抓取裁决",
    )
    parser.add_argument("--rebuild-cache", action="store_true", help="已停用：缓存只允许按当天单期顺序滚动")
    parser.add_argument("--diagnose", action="store_true", help="全站真实抓取但不写成功TXT、失败TXT或缓存")
    parser.add_argument("--multi-mode", action="store_true", help=argparse.SUPPRESS)
    parser.set_defaults(verify_ssl=True)
    parser.add_argument("--verify-ssl", dest="verify_ssl", action="store_true", help="校验证书（默认开启）")
    parser.add_argument("--no-verify-ssl", dest="verify_ssl", action="store_false", help="不校验证书；仅人工确认需要时使用")
    return parser


def resolve_inputs(args: argparse.Namespace) -> tuple[str | None, str, str]:
    target_input = args.target
    issues_input = args.issues
    sites_input = args.sites
    positional = list(args.pos_args)

    if len(positional) > 3:
        raise ValueError("参数太多。常用格式：python bantou_crawler.py 120 sites.json")

    if positional:
        if len(positional) == 1:
            if issues_input is None:
                issues_input = positional[0]
        elif len(positional) == 2:
            if VALUE_RE.search(normalize_text(positional[0])):
                if target_input is None:
                    target_input = positional[0]
                if issues_input is None:
                    issues_input = positional[1]
            else:
                if issues_input is None:
                    issues_input = positional[0]
                if sites_input is None:
                    sites_input = positional[1]
        else:
            if target_input is None:
                target_input = positional[0]
            if issues_input is None:
                issues_input = positional[1]
            if sites_input is None:
                sites_input = positional[2]

    if issues_input is None:
        raise ValueError("必须手动指定期数，例子：python bantou_crawler.py 147")

    if sites_input is None:
        sites_input = DEFAULT_SITES_FILE

    return target_input, issues_input, sites_input
