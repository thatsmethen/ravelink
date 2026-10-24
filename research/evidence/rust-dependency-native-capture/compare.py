#!/usr/bin/env python3
"""Compare current locked shipping package membership with frozen audit evidence.

Offline only, no advisory/yank refresh and no dependency changes. Python 3.11+.
An output directory must be new; frozen observations are never overwritten.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[3]
TARGETS = ("aarch64-apple-darwin", "x86_64-apple-darwin", "x86_64-pc-windows-msvc")
GRAPHS = (("app-all", "normal,build", "ravelink-app"),
          ("app-runtime", "normal,no-proc-macro", "ravelink-app"),
          ("hal-all", "normal,build", "ravelink-hal"))
CRATES_IO = "registry+https://github.com/rust-lang/crates.io-index"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(command, root):
    result = subprocess.run(command, cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="strict", timeout=60)
    if result.returncode:
        raise RuntimeError(f"command failed ({result.returncode}): {command}\n{result.stderr}")
    return result


def membership(text):
    return set(re.findall(r"^([\w-]+) v([^\s]+)", text, re.MULTILINE))


def packages(lock):
    result = {}
    for item in tomllib.loads(lock.decode("utf-8"))["package"]:
        key = (item["name"], item["version"], item.get("source", "workspace"))
        if key in result:
            raise ValueError(f"duplicate lock package: {key}")
        result[key] = item
    return result


def named(items):
    return [dict(name=name, version=version) for name, version in sorted(items)]


def compare(args):
    root, baseline, output = args.root.resolve(), args.baseline.resolve(), args.output.resolve()
    # Validate every retained baseline byte, then repeat the hashes after the
    # comparison so new observations cannot silently alter historical evidence.
    manifest_bytes = (baseline / "SHA256SUMS.json").read_bytes()
    baseline_hashes = json.loads(manifest_bytes)
    for name, expected in baseline_hashes.items():
        if sha((baseline / name).read_bytes()) != expected:
            raise ValueError(f"frozen evidence hash mismatch: {name}")
    baseline_input = json.loads((baseline / "script-validation-utf8/input.json").read_text(encoding="utf-8"))
    old_lock = (baseline / "Cargo.lock.snapshot").read_bytes()
    if sha(old_lock) != baseline_input["lockfile_sha256"]:
        raise ValueError("historical lock hash mismatch")
    output.mkdir(parents=True, exist_ok=False)
    lock = (root / "Cargo.lock").read_bytes()
    (output / "Cargo.lock.snapshot").write_bytes(lock)
    inputs = [Path("Cargo.toml"), *[p.relative_to(root) for p in sorted((root / "crates").glob("*/Cargo.toml"))]]
    inputs += [Path("rust-toolchain.toml")]
    inputs += [Path("crates/ravelink-audio/src") / name for name in
               ("native_capture.rs", "native_packet.rs", "native_timing.rs", "native_capture_tests.rs", "native_packet_tests.rs")]
    hashes = {str(path): sha((root / path).read_bytes()) for path in inputs}
    for path in inputs:
        target = output / "inputs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / path).read_bytes())
    provenance = {
        "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "repository_head_at_start": run(["git", "rev-parse", "HEAD"], root).stdout.strip(),
        "scope": "uncommitted frozen native capture candidate, identified by retained file hashes",
        "old_lockfile_sha256": sha(old_lock), "new_lockfile_sha256": sha(lock),
        "baseline_manifest_sha256": sha(manifest_bytes), "baseline_verified_files": len(baseline_hashes),
        "baseline": str(baseline.relative_to(root)), "input_sha256": hashes,
        "cargo_version": run(["cargo", "--version"], root).stdout.strip(),
        "rustc_version": run(["rustc", "--version"], root).stdout.strip(),
        "script_sha256": sha(Path(__file__).read_bytes()), "network_access": False,
    }
    write_json(output / "input.json", provenance)
    old_packages, new_packages = packages(old_lock), packages(lock)
    package_changes = {
        "old_count": len(old_packages), "new_count": len(new_packages),
        "added": sorted(set(new_packages) - set(old_packages)),
        "removed": sorted(set(old_packages) - set(new_packages)),
        "changed_checksums": [key for key in sorted(set(old_packages) & set(new_packages))
                              if old_packages[key].get("checksum") != new_packages[key].get("checksum")],
        "changed_dependency_lists": [key for key in sorted(set(old_packages) & set(new_packages))
                                     if old_packages[key].get("dependencies", []) != new_packages[key].get("dependencies", [])],
    }
    graph_comparisons, commands, current_graphs = [], [], {}
    for target in TARGETS:
        for label, edges, package in GRAPHS:
            name = f"{target}-{label}.txt"
            command = ["cargo", "tree", "--offline", "--locked", "--color", "never", "-p", package,
                       "--target", target, "--edges", edges, "--prefix", "none", "--format", "{p}"]
            result = run(command, root)
            (output / name).write_text(result.stdout, encoding="utf-8")
            previous = membership((baseline / "script-validation-utf8" / name).read_text(encoding="utf-8"))
            current = membership(result.stdout)
            if (package, "0.1.0") not in current:
                raise ValueError(f"missing graph root in {name}")
            current_graphs[target, label] = current
            graph_comparisons.append({"target": target, "graph": label, "old_count": len(previous),
                                     "new_count": len(current), "added": named(current - previous),
                                     "removed": named(previous - current), "members": named(current)})
            commands.append({"command": command, "exit_code": result.returncode,
                             "stdout": name, "stderr": result.stderr})
    selected = set().union(*(value for (target, label), value in current_graphs.items() if label.endswith("-all")))
    selected_registry = []
    for name, version in sorted(selected):
        matches = [item for (n, v, _), item in new_packages.items() if n == name and v == version]
        if len(matches) != 1:
            raise ValueError(f"ambiguous or absent locked package: {name} {version}")
        if matches[0].get("source") == CRATES_IO:
            selected_registry.append(matches[0])
        elif matches[0].get("source"):
            raise ValueError(f"non-crates.io external package requires separate coverage: {name}")
    yanks = json.loads((baseline / "fresh-yanks-2026-10-24-followup/results.json").read_text(encoding="utf-8"))
    prior_yanks = {(p["name"], p["version"]): p for p in yanks}
    uncovered = [dict(name=p["name"], version=p["version"]) for p in selected_registry
                 if (p["name"], p["version"]) not in prior_yanks or
                 prior_yanks[p["name"], p["version"]]["locked_checksum"] != p["checksum"]]
    findings = json.loads((baseline / "script-validation-utf8/target-membership.json").read_text(encoding="utf-8"))
    for finding in findings:
        finding["historical_targets"] = finding.pop("targets")
        key = (finding["package"], finding["version"])
        finding["candidate_targets"] = {target: {label: key in current_graphs[target, label]
                                                for label, _, _ in GRAPHS} for target in TARGETS}
    unchanged = not any(package_changes[key] for key in ("added", "removed", "changed_checksums"))
    summary = {
        "lock_packages": package_changes,
        "all_package_identities_and_checksums_unchanged": unchanged,
        "graph_membership_unchanged": all(not item["added"] and not item["removed"] for item in graph_comparisons),
        "selected_registry_versions": len(selected_registry), "uncovered_by_historical_yank_records": uncovered,
        "historical_observations_cover_current_selected_versions": unchanged and not uncovered,
        "security_status_refreshed": False,
        "limitations": ["This is an offline package-membership comparison, not a new advisory or yank audit.",
                        "Historical records cover package versions at their original observations, not current security/yank status.",
                        "Feature sets, dependency edges, function reachability, generated output and binary behavior are not proven equivalent.",
                        "Rust std/core/compiler builtins, system SDKs/libraries and the separately locked dependency-free Windows kernel crate are outside this root-lock comparison."],
    }
    if sha((root / "Cargo.lock").read_bytes()) != sha(lock) or any(sha((root / path).read_bytes()) != value for path, value in hashes.items()):
        raise ValueError("candidate inputs changed during comparison")
    if sha((baseline / "SHA256SUMS.json").read_bytes()) != sha(manifest_bytes) or any(sha((baseline / name).read_bytes()) != value for name, value in baseline_hashes.items()):
        raise ValueError("historical evidence changed during comparison")
    write_json(output / "graph-commands.json", commands)
    write_json(output / "graph-comparison.json", graph_comparisons)
    write_json(output / "historical-advisory-membership.json", findings)
    write_json(output / "summary.json", summary)
    write_json(output / "SHA256SUMS.json", {str(p.relative_to(output)): sha(p.read_bytes()) for p in sorted(output.rglob("*")) if p.is_file()})
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if unchanged and not uncovered else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--baseline", type=Path, default=ROOT / "research/evidence/rust-dependency-audit")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        return compare(args)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Comparison unavailable: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
