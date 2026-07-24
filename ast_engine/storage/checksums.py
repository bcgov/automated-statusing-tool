# ast/ast_engine/storage/checksums.py

import hashlib
from pathlib import Path


def sha256_file(path: Path) -> str:
    # create checksum of the file
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def write_sha256_sidecar(path: Path) -> Path:
    # create a sidecar file with the SHA-256 checksum of the file
    checksum = sha256_file(path)
    sidecar = path.with_name(f"{path.name}.sha256")
    sidecar.write_text(f"{checksum}  {path.name}\n", encoding="utf-8")
    return sidecar