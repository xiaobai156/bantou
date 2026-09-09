from __future__ import annotations

from bantou.domain.models import SourceDocument
from bantou.parsers.dedicated import guangdong_baer_left_half_head_matches

URL = "https://besjbec.6328v-8pwlk-jzhgyz.work:16677/#am"


def report(label: str, html: str) -> None:
    doc = SourceDocument(
        html,
        source_url=URL,
        source_kind="browser",
        container_id=label,
        document_authority="declared-rendered-container",
    )
    matches = guangdong_baer_left_half_head_matches([doc], {252})
    print(
        f"STATE\t{label}\tlen={len(html)}\t"
        f"title={'『半波半头』' in html}\t252={'252期' in html}\t"
        f"matches={[(m.value, m.snippet) for m in matches]}"
    )
    for needle in ("『半波半头』", "252期"):
        pos = html.find(needle)
        if pos >= 0:
            print(f"WIN\t{label}\t{needle}\t{html[max(0,pos-300):pos+1500].replace(chr(10),' ')[:1800]}")


def main() -> None:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for wait in ("domcontentloaded", "load"):
                context = browser.new_context(service_workers="block")
                page = context.new_page()
                page.set_default_timeout(30000)
                try:
                    page.goto(URL, wait_until=wait, timeout=30000)
                    report(f"{wait}-0", page.content())
                    for ms in (500, 1500, 3000, 6000):
                        page.wait_for_timeout(ms if ms == 500 else ms - (500 if ms == 1500 else 1500 if ms == 3000 else 3000))
                        report(f"{wait}-{ms}", page.content())
                except Exception as exc:
                    print(f"ERROR\t{wait}\t{type(exc).__name__}: {exc}")
                finally:
                    context.close()

            context = browser.new_context(service_workers="block")
            page = context.new_page()
            try:
                page.goto(URL, wait_until="networkidle", timeout=30000)
                report("networkidle", page.content())
            except Exception as exc:
                print(f"ERROR\tnetworkidle\t{type(exc).__name__}: {exc}")
            finally:
                context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()
