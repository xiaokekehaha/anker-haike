"""haike-db：upgrade / current / check（票 47）。"""

from __future__ import annotations

import argparse
import sys

from app.db.migrations import SchemaOutOfDate, current_revision, head_revision, upgrade_to_head
from app.settings import settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="业务表迁移")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("upgrade", help="升级到 head（空库一条命令建齐）")
    sub.add_parser("current", help="打印库内版本与代码 head")
    sub.add_parser("check", help="版本不一致时非零退出（CI / 启动前）")
    ns = ap.parse_args(sys.argv[1:] if argv is None else argv)
    head = head_revision()
    if ns.cmd == "upgrade":
        before = current_revision()
        upgrade_to_head()
        print(f"upgraded {before or 'empty'} -> {current_revision()} (head {head})")
        return 0
    cur = current_revision()
    print(f"database={cur or 'empty'} head={head} url={_redact(settings.database_url)}")
    if ns.cmd == "check" and cur != head:
        print(str(SchemaOutOfDate(cur, head)), file=sys.stderr)
        return 1
    return 0


def _redact(url: str) -> str:
    if "@" not in url:
        return url
    a, b = url.split("@", 1)
    return a.split("//", 1)[0] + "//***@" + b


if __name__ == "__main__":
    raise SystemExit(main())
