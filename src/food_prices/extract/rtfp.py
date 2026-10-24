"""Locate and fingerprint the RTFP release dropped into data/landing/."""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from food_prices import config


def parse_version(path: Path) -> date:
    """'KEN_RTFP_mkt_2007_2026-08-24.csv' -> date(2026, 8, 24). The date is the release version."""
    m = config.FILE_PATTERN.match(path.name)
    if not m:
        raise ValueError(f"Unexpected file name: {path.name}")
    return date.fromisoformat(m.group(1))


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def list_landing_files(landing_dir: Path | None = None) -> list[Path]:
    """Release files in the landing folder, oldest version first."""
    landing_dir = landing_dir or config.LANDING_DIR
    files = [p for p in landing_dir.glob("*.csv") if config.FILE_PATTERN.match(p.name)]
    return sorted(files, key=parse_version)


def file_info(path: Path) -> dict:
    return {
        "file_name": path.name,
        "source_version": parse_version(path).isoformat(),
        "file_sha256": sha256_file(path),
        "downloaded_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat(),
        "source_url": config.SOURCE_REF,
    }


def already_loaded(engine: Engine, version: date, sha256: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT file_sha256 FROM metadata.lineage WHERE source_version = :v"),
            {"v": version},
        ).first()
    return row is not None and row[0] == sha256


def find_new_release(engine: Engine | None = None, landing_dir: Path | None = None) -> Path | None:
    """Newest landing file that is not yet loaded (same version AND same hash). None => nothing to do."""
    engine = engine or config.get_engine()
    files = list_landing_files(landing_dir)
    if not files:
        return None
    newest = files[-1]
    if already_loaded(engine, parse_version(newest), sha256_file(newest)):
        return None
    return newest
