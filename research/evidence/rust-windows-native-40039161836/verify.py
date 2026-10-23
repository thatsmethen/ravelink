#!/usr/bin/env python3
"""Verify retained evidence bytes without extracting or executing the driver."""
import hashlib
import json
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
manifest = json.loads((root / "custody.json").read_text(encoding="utf-8"))


def verify_bytes(data, record):
    assert len(data) == record["bytes"], f"size mismatch: {record['path']}"
    assert hashlib.sha256(data).hexdigest() == record["sha256"], record["path"]


for record in manifest["files"]:
    verify_bytes((root / record["path"]).read_bytes(), record)
api = json.loads((root / "artifact-api.json").read_bytes())
assert api["workflow_run"]["head_sha"] == manifest["head_sha"]
assert api["workflow_run"]["id"] == manifest["run_id"]
assert api["id"] == manifest["artifact"]["id"]
archive_bytes = (root / "artifact-original.zip").read_bytes()
assert "sha256:" + hashlib.sha256(archive_bytes).hexdigest() == api["digest"]
with zipfile.ZipFile(root / "artifact-original.zip") as archive:
    records = {item["path"]: item for item in manifest["archive_members"]}
    names = archive.namelist()
    assert len(names) == len(set(names)) == len(records) == 16
    assert set(names) == set(records)
    for name, record in records.items():
        verify_bytes(archive.read(name), record)
    pe = json.loads(archive.read("pe-evidence.json"))
    assert hashlib.sha256(archive.read("RaveLink.sys")).hexdigest() == pe["sha256"]
    build = json.loads(archive.read("build-evidence.json"))
    assert build["signed"] is False and build["kernel_loaded"] is False
    assert build["catalog_created"] is True
print("Verified 6 retained originals, 16 archive members, GitHub digest and driver hash.")
