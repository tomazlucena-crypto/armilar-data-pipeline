from __future__ import annotations

import zipfile
from pathlib import Path

from .util import sha256_file, utc_now


def write_checksums(run_root: str | Path) -> Path:
    run_dir = Path(run_root)
    checksum_file = run_dir / "SHA256SUMS"
    lines: list[str] = []
    for path in sorted(run_dir.rglob("*")):
        if not path.is_file() or path == checksum_file:
            continue
        relative = path.relative_to(run_dir).as_posix()
        lines.append(f"{sha256_file(path)}  {relative}")
    checksum_file.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return checksum_file


def create_bundle(run_root: str | Path, output_dir: str | Path) -> Path:
    run_dir = Path(run_root)
    if not run_dir.is_dir():
        raise FileNotFoundError(f"Run directory does not exist: {run_dir}")
    write_checksums(run_dir)
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now().replace("-", "").replace(":", "")
    bundle_path = target_dir / f"armilar_data_{stamp}.zip"
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(run_dir.rglob("*")):
            if path.is_file():
                archive.write(path, arcname=path.relative_to(run_dir).as_posix())
    return bundle_path
