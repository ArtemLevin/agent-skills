#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import io
import os
import tarfile
import tempfile
from pathlib import Path


def normalize_sdist(path: Path, *, epoch: int) -> None:
    entries: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:gz") as source:
        for member in source.getmembers():
            stream = source.extractfile(member) if member.isfile() else None
            entries.append((member, stream.read() if stream is not None else None))

    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(raw)
    try:
        with temporary.open("wb") as output:
            with gzip.GzipFile(filename="", mode="wb", fileobj=output, mtime=epoch) as compressed:
                with tarfile.open(
                    fileobj=compressed,
                    mode="w",
                    format=tarfile.GNU_FORMAT,
                ) as target:
                    for member, data in entries:
                        member.mtime = epoch
                        member.uid = 0
                        member.gid = 0
                        member.uname = ""
                        member.gname = ""
                        member.pax_headers = {}
                        target.addfile(
                            member,
                            io.BytesIO(data) if data is not None else None,
                        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument(
        "--epoch",
        type=int,
        default=int(os.environ.get("SOURCE_DATE_EPOCH", "0")),
    )
    args = parser.parse_args()
    if args.epoch <= 0:
        parser.error("provide --epoch or SOURCE_DATE_EPOCH")
    for path in args.paths:
        normalize_sdist(path, epoch=args.epoch)
        print(f"normalized {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
