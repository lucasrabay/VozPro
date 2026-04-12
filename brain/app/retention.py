from __future__ import annotations

import asyncio
import os
import shutil
from pathlib import Path

from . import db
from .logging_config import get_logger

DATA_RETENTION_DAYS = int(os.environ.get("BIU_DATA_RETENTION_DAYS", "90"))
PDF_RETENTION_DAYS = int(os.environ.get("BIU_PDF_RETENTION_DAYS", "30"))
PDF_DIR = os.environ.get("BIU_PDF_DIR", "./data/pdfs")
MIN_FREE_MB = 500

log = get_logger("retention")


def free_space_mb(path: str) -> int:
    try:
        total, used, free = shutil.disk_usage(path)
        return free // (1024 * 1024)
    except OSError:
        return -1


def cleanup_once() -> dict[str, int]:
    removed_convs = 0
    removed_pdfs = 0
    orphan_pdfs_removed = 0

    with db.connect() as conn:
        cur = conn.execute(
            "DELETE FROM conversations WHERE updated_at < datetime('now', ?)",
            (f"-{DATA_RETENTION_DAYS} days",),
        )
        removed_convs = cur.rowcount

        old_pdfs = [
            row["pdf_path"]
            for row in conn.execute(
                "SELECT pdf_path FROM curriculos WHERE created_at < datetime('now', ?)",
                (f"-{PDF_RETENTION_DAYS} days",),
            )
        ]
        conn.execute(
            "DELETE FROM curriculos WHERE created_at < datetime('now', ?)",
            (f"-{PDF_RETENTION_DAYS} days",),
        )

    for p in old_pdfs:
        try:
            Path(p).unlink(missing_ok=True)
            removed_pdfs += 1
        except OSError as e:
            log.warning("pdf_unlink_failed", path=p, error=str(e))

    pdf_root = Path(PDF_DIR)
    if pdf_root.exists():
        with db.connect() as conn:
            known = {row["pdf_path"] for row in conn.execute("SELECT pdf_path FROM curriculos")}
        for f in pdf_root.glob("*.pdf"):
            if str(f) not in known and _age_days(f) > PDF_RETENTION_DAYS:
                try:
                    f.unlink()
                    orphan_pdfs_removed += 1
                except OSError:
                    pass

    free = free_space_mb(PDF_DIR)
    if 0 < free < MIN_FREE_MB:
        log.warning("low_disk_space", free_mb=free, threshold_mb=MIN_FREE_MB)

    log.info(
        "retention_cleanup_done",
        removed_conversations=removed_convs,
        removed_pdfs=removed_pdfs,
        orphan_pdfs_removed=orphan_pdfs_removed,
        free_mb=free,
    )
    return {
        "removed_conversations": removed_convs,
        "removed_pdfs": removed_pdfs,
        "orphan_pdfs_removed": orphan_pdfs_removed,
    }


def _age_days(path: Path) -> float:
    import time

    try:
        return (time.time() - path.stat().st_mtime) / 86400.0
    except OSError:
        return 0.0


async def retention_loop(interval_seconds: int = 86400) -> None:
    while True:
        try:
            cleanup_once()
        except Exception as e:
            log.error("retention_loop_error", error=str(e))
        await asyncio.sleep(interval_seconds)
