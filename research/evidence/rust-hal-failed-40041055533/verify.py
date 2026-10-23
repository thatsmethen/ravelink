#!/usr/bin/env python3
"""Verify retained originals and the runner's custody manifest without extraction."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
record = json.loads((root / "preservation.json").read_text())
for file in record["original_files"]:
    data = (root / file["path"]).read_bytes()
    assert len(data) == file["bytes"], file["path"]
    assert hashlib.sha256(data).hexdigest() == file["sha256"], file["path"]
with zipfile.ZipFile(root / "artifact-original.zip") as archive:
    members = {name: archive.read(name) for name in archive.namelist() if not name.endswith("/")}
    assert set(members) == {file["path"] for file in record["archive_members"]}
    for file in record["archive_members"]:
        data = members[file["path"]]
        assert len(data) == file["bytes"], file["path"]
        assert hashlib.sha256(data).hexdigest() == file["sha256"], file["path"]
    manifest = json.loads(members["custody-manifest.json"])
    assert manifest["source_revision"] == record["head_sha"]
    for file in manifest["files"]:
        data = members[file["path"]]
        assert len(data) == file["bytes"], file["path"]
        assert hashlib.sha256(data).hexdigest() == file["sha256"], file["path"]
assert record["github_digest"] == "sha256:" + record["original_zip_sha256"]
print(f"Verified {len(members)} original archive members and {len(manifest['files'])} runner custody records.")
