#!/usr/bin/env python3
"""Offline checks of dependency-audit decoding and fail-closed yank evidence."""

import email.message
import gzip
import hashlib
import http.client
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch


def load(filename, name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


audit = load("audit-dependencies.py", "advisory_audit")
yanks = load("audit-dependencies-yanks.py", "yank_audit")
CHECKSUM = "a" * 64
PACKAGE = {"name": "fixture", "version": "1.2.3", "checksum": CHECKSUM, "targets": {}}


def row(**changes):
    return {"name": "fixture", "vers": "1.2.3", "cksum": CHECKSUM, "yanked": False, **changes}


def body(*rows):
    return ("\n".join(json.dumps(item) for item in rows) + "\n").encode("utf-8")


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = email.message.Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value


class AuditTests(unittest.TestCase):
    def test_utf8_decoding_and_invalid_byte_failure_are_explicit(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = audit.run([sys.executable, "-c", "import sys;sys.stdout.buffer.write(bytes([0xc3,0xa9]))"], cwd)
            self.assertEqual(result.stdout, "é")
            with self.assertRaises(UnicodeDecodeError):
                audit.run([sys.executable, "-c", "import sys;sys.stdout.buffer.write(bytes([0xff]))"], cwd)

    def test_corrupt_cached_tool_never_executes(self):
        pins = json.loads(audit.PINS.read_text(encoding="utf-8"))
        target = "aarch64-apple-darwin"
        with tempfile.TemporaryDirectory() as folder:
            cache = Path(folder)
            (cache / pins["assets"][target]["filename"]).write_bytes(b"untrusted executable archive")
            with patch.object(audit, "host_target", return_value=target), patch.object(audit, "run") as execute:
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    audit.acquire_tool(pins, cache)
                execute.assert_not_called()

    def test_sparse_path_contract_and_path_rejection(self):
        for name, expected in (("a", "1/a"), ("ab", "2/ab"), ("AbC", "3/a/abc"), ("serde", "se/rd/serde")):
            self.assertEqual(yanks.index_path(name), expected)
        for name in ("", "../a", "a/b", "a?b", "é", "a" * 65):
            with self.assertRaises(ValueError):
                yanks.index_path(name)

    def test_normal_yanked_and_checksum_mismatch_remain_distinct(self):
        for data, expected in ((row(), "not_yanked"), (row(yanked=True), "yanked"), (row(cksum="b" * 64), "checksum_mismatch")):
            result = yanks.evaluate("fixture", [PACKAGE], body(data))
            self.assertEqual(result[0]["status"], expected)

    def test_missing_duplicate_malformed_or_future_rows_never_pass(self):
        cases = (body(row(vers="1.2.2")), body(row(), row()), body(row(), row(vers="1.2.3+other")),
                 body(row(yanked="false")), body(row(yanked=None)), body(row(v=3)), body(row(v=True)), body(row(cksum="bad")))
        for data in cases:
            self.assertEqual(yanks.evaluate("fixture", [PACKAGE], data)[0]["status"], "unavailable")
        for data in (b"\xff", b"{}\nnot json", body(row(name="another")), b""):
            with self.assertRaises(ValueError):
                yanks.evaluate("fixture", [PACKAGE], data)

    def test_one_index_response_checks_each_locked_version(self):
        second = {**PACKAGE, "version": "2.0.0"}
        result = yanks.evaluate("fixture", [PACKAGE, second], body(row(), row(vers="2.0.0", yanked=True)))
        self.assertEqual([item["status"] for item in result], ["not_yanked", "yanked"])

    def test_graph_scope_requires_matching_custody_hashes(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            lock = ('version = 3\n[[package]]\nname = "fixture"\nversion = "1.2.3"\n'
                    f'source = "{yanks.REGISTRY}"\nchecksum = "{CHECKSUM}"\n').encode()
            (directory / "Cargo.lock.snapshot").write_bytes(lock)
            yanks.write_json(directory / "input.json", {"lockfile_sha256": yanks.sha(lock)})
            yanks.write_json(directory / "summary.json", {"audit_exit_code": 1})
            for target in yanks.TARGETS:
                for label in ("app-all", "app-runtime", "hal-all"):
                    (directory / f"{target}-{label}.txt").write_text("fixture v1.2.3\n", encoding="utf-8")
            yanks.write_json(directory / "SHA256SUMS.json", {path.name: yanks.sha(path.read_bytes()) for path in directory.iterdir()})
            scope, captured = yanks.load_scope(directory)
            self.assertEqual(captured, lock)
            self.assertEqual(len(scope["selected_packages"]), 1)
            (directory / "Cargo.lock.snapshot").write_bytes(lock + b"# altered after capture\n")
            with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                yanks.load_scope(directory)

    def fetch(self, response, limits=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        output = Path(directory.name)
        (output / "responses").mkdir()
        opener = Mock()
        opener.open.return_value = response
        result, data = yanks.fetch("fixture", "fi/xt/fixture", output, limits or yanks.Limits(interval=0), opener)
        return result, data, output, opener

    def test_http_bytes_and_headers_are_retained_without_conditionals(self):
        data = body(row())
        result, actual, output, opener = self.fetch(Response(data, headers={"ETag": '"test"', "Age": "3", "Content-Length": str(len(data))}))
        self.assertEqual(actual, data)
        self.assertEqual(result["status"], "observed")
        self.assertTrue(result["body_complete"])
        self.assertEqual(gzip.decompress((output / result["body_file"]).read_bytes()), data)
        self.assertEqual(result["body_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(result["headers"]["age"], "3")
        headers = {name.lower(): value for name, value in opener.open.call_args.args[0].header_items()}
        self.assertNotIn("if-none-match", headers)
        self.assertNotIn("if-modified-since", headers)
        self.assertEqual(headers["cache-control"], "no-cache, max-age=0")

    def test_non_200_truncated_encoded_and_broken_http_are_unavailable(self):
        fixtures = (Response(b"not found", status=404), Response(b"", status=304),
                    Response(b"short", headers={"Content-Length": "100"}), Response(b"compressed", headers={"Content-Encoding": "gzip"}))
        for response in fixtures:
            result, actual, _, _ = self.fetch(response)
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(actual)
        broken = Response(b"")
        broken.read1 = Mock(side_effect=http.client.IncompleteRead(b"partial"))
        result, actual, _, _ = self.fetch(broken)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(actual)

    def test_rate_limit_stops_later_requests_and_records_retry_after(self):
        limits = yanks.Limits(interval=0)
        result, _, output, _ = self.fetch(Response(b"wait", status=429, headers={"Retry-After": "120"}), limits)
        self.assertEqual(result["headers"]["retry-after"], "120")
        opener = Mock()
        subsequent, data = yanks.fetch("second", "se/co/second", output, limits, opener)
        opener.open.assert_not_called()
        self.assertIsNone(data)
        self.assertEqual(subsequent["status"], "unavailable")

    def test_byte_and_deadline_budgets_fail_closed(self):
        result, data, _, _ = self.fetch(Response(b"abcdef"), yanks.Limits(interval=0, total=3))
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(data)
        self.assertEqual(result["body_bytes"], 3)
        result, _, _, opener = self.fetch(Response(b""), yanks.Limits(interval=0, seconds=0))
        opener.open.assert_not_called()
        self.assertEqual(result["status"], "unavailable")
        with patch.object(yanks, "MAX_RESPONSE", 3):
            result, data, _, _ = self.fetch(Response(b"abcdef"))
        self.assertEqual(result["body_bytes"], 4)
        self.assertIsNone(data)

    def test_incomplete_outranks_findings_and_advisory_warnings_are_preserved(self):
        clean = [{"status": "not_yanked"}]
        summary = yanks.summarize(clean, 1)
        self.assertEqual((summary["yank_exit_code"], summary["combined_exit_code"]), (0, 1))
        result = yanks.summarize([{"status": "yanked"}, {"status": "unavailable"}], 1)
        self.assertEqual((result["yank_exit_code"], result["combined_exit_code"]), (2, 2))
        self.assertEqual(result["counts"]["yanked"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
