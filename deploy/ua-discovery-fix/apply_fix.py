#!/usr/bin/env python3
"""Apply serper-only discovery fix to ua_materialy_scraper.py."""
# trigger: auto-deploy via push to main
from __future__ import annotations

import sys
from pathlib import Path

OLD_BLOCK = """            if serper_only and ENABLE_CLAUDE_PAGE_VERIFY:
                r = enrich_row_with_contacts(r, cache, logger)
                if not r.get("retail_verified"):
                    reason = (r.get("verification_reason") or "claude_rejected").strip()
                    console_step(
                        f"Claude: odrzucono ({reason}): {r.get('nazwa', '')}"
                    )
                    if funnel is not None:
                        funnel["rejected_claude_verify"] = (
                            funnel.get("rejected_claude_verify", 0) + 1
                        )
                    continue
            elif serper_only:
                r["retail_verified"] = False
                r["verification_reason"] = PENDING_WWW_VERIFY_REASON
                r["email_target"] = ""
                r["email_status"] = "pending_www_verify\""""

NEW_BLOCK = """            if serper_only:
                # Pon–pt (--serper-only-discovery): zapis pending_www_verify;
                # pełny crawl + Claude verify w niedzielę (--verify-pending-contacts).
                r["retail_verified"] = False
                r["verification_reason"] = PENDING_WWW_VERIFY_REASON
                r["email_target"] = ""
                r["email_status"] = "pending_www_verify\""""

OLD_CACHE_GUARD = """            if serper_only and not (
                ENABLE_CLAUDE_PAGE_VERIFY and r.get("retail_verified")
            ):"""

NEW_CACHE_GUARD = """            if serper_only:"""

OLD_PENDING_CALL = """        return is_serper_only_pending_candidate(
            email=email, url=url, name=name, text=text
        )"""

NEW_PENDING_CALL = """        return is_serper_only_pending_candidate(
            url=url, name=name, text=text
        )"""


def apply(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if NEW_BLOCK.splitlines()[0] in text and OLD_BLOCK not in text:
        print(f"Already patched: {path}")
        return
    if OLD_BLOCK not in text:
        raise SystemExit(f"Expected code block not found in {path}")
    text = text.replace(OLD_BLOCK, NEW_BLOCK, 1)
    text = text.replace(OLD_CACHE_GUARD, NEW_CACHE_GUARD, 1)
    text = text.replace(OLD_PENDING_CALL, NEW_PENDING_CALL, 1)
    path.write_text(text, encoding="utf-8")
    print(f"Patched: {path}")


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "ua_materialy_scraper.py")
    apply(target)
