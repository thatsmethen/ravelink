#!/usr/bin/env python3
"""Verify original release archives and every frozen manifest member, without extraction."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import zipfile

SOURCE = "a4b21a393b1b1a9929d16da5d4e8ad0cea5cbfc7"
ROOT = Path(__file__).resolve().parent


def verify(archives):
    results = []
    api = json.loads((ROOT / "original-artifacts.json").read_text())["artifacts"]
    for label in ("runtime", "hal"):
        frozen = json.loads((ROOT / f"{label}-custody-verification.json").read_text())
        path = archives / frozen["archive"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        asset = next(a for a in api if a["id"] == frozen["artifact_id"])
        if path.stat().st_size != frozen["bytes"] or digest != frozen["sha256"] or asset["digest"] != "sha256:" + digest:
            raise ValueError(f"Archive bytes/hash differ: {label}")
        actual = {}
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                relative = PurePosixPath(member.filename)
                if relative.is_absolute() or ".." in relative.parts or member.filename in actual or stat.S_ISLNK(member.external_attr >> 16):
                    raise ValueError("Unsafe or repeated archive member")
                if member.is_dir():
                    raise ValueError("Unexpected directory member in frozen archive")
                data = archive.read(member)
                actual[member.filename] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            manifest = json.loads(archive.read("custody-manifest.json"))
        expected = {row["path"]: {"bytes": row["bytes"], "sha256": row["sha256"]} for row in manifest["files"]}
        if len(expected) != len(manifest["files"]) or manifest["source_revision"] != SOURCE:
            raise ValueError("Invalid manifest source/duplicates")
        actual.pop("custody-manifest.json")
        if actual != expected or len(actual) != frozen["manifest_file_count"]:
            raise ValueError(f"Manifest members/bytes/hash differ: {label}")
        results.append({"archive": path.name, "bytes": path.stat().st_size, "sha256": digest,
                        "manifest_files_verified": len(actual), "source_revision": SOURCE})
    return {"pass": True, "archives": results,
            "scope": "Original archive and member custody only; installed runtime FAILED, separate basic HAL observation PASSED."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archives", type=Path, default=ROOT)
    print(json.dumps(verify(parser.parse_args().archives), indent=2))
