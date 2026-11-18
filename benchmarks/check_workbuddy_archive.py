"""Roundtrip captured wire bytes, metadata, multipart transfer and fail-closed guards."""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from package_workbuddy import make_archive, production, sha, split_archive, verify_archive
from restore_workbuddy import extract, join_parts


def rejected(action):
    try:
        action()
    except (ValueError, FileExistsError):
        return
    raise AssertionError("Operation should have been rejected")


def check(sample):
    checks = []
    with tempfile.TemporaryDirectory(prefix="wb-archive-check-") as temporary:
        root = Path(temporary)
        base = root / "workbuddy-codex-fixture"
        base.mkdir()
        for name in ("request.raw.json", "request.sent.json", "response.raw", "receipt.json"):
            shutil.copyfile(sample / name, base / name)
        (base / "副本").mkdir()
        shutil.copyfile(base / "response.raw", base / "副本" / "response.raw")
        (base / "空目录").mkdir()
        (base / "empty").touch()
        (base / "中文.txt").write_text("保留原始轨迹\n", encoding="utf-8")
        (base / "tool").write_bytes(b"#!/bin/sh\nexit 0\n")
        (base / "tool").chmod(0o751)
        (base / "relative-link").symlink_to("中文.txt")
        (base / "directory-link").symlink_to("副本", target_is_directory=True)
        os.utime(base / "tool", ns=(1_600_000_000_000_000_000,) * 2)
        expected = {f"{base.name}/{p.relative_to(base)}": {"size": p.stat().st_size, "sha256": sha(p)}
                    for p in base.rglob("*") if p.is_file() and not p.is_symlink()}
        archive = root / "fixture.zip"
        header = make_archive(base, archive, expected=expected, chunk_size=4096)
        verified = verify_archive(archive)
        assert header["logical_bytes"] > header["unique_chunk_bytes"]
        checks.append("real captured wire bytes and duplicate-content chunking")
        export = root / "export"
        manifest = split_archive(archive, export, part_size=8192)
        assert len(manifest["parts"]) > 1
        rejoined = join_parts(export)
        assert sha(rejoined) == sha(archive) == verified["archive_sha256"]
        checks.append("multipart SHA validation and exact rejoin")
        restored = root / "restored"
        result = extract(rejoined, restored)
        for path in base.rglob("*"):
            target = restored / base.name / path.relative_to(base)
            if path.is_symlink():
                assert target.is_symlink() and os.readlink(path) == os.readlink(target)
            elif path.is_file():
                assert sha(path) == sha(target)
                assert path.stat().st_mode & 0o777 == target.stat().st_mode & 0o777
                assert path.stat().st_mtime_ns == target.stat().st_mtime_ns
            else:
                assert target.is_dir()
        assert result["restored_symlinks"] == 2
        checks.append("Unicode, empty files/directories, executable mode, timestamp and symlinks")
        rejected(lambda: extract(rejoined, restored))
        checks.append("refuse overwriting an existing restore directory")
        first = export / "archive" / manifest["parts"][0]["path"]
        data = first.read_bytes()
        first.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        rejoined.unlink()
        rejected(lambda: join_parts(export))
        checks.append("reject tampered multipart content")
        canary = b"fixture-secret-only-0123456789"
        (base / "canary").write_bytes(b"x" * 4090 + canary)
        rejected(lambda: make_archive(base, root / "canary.zip", secrets=[canary], chunk_size=4096))
        checks.append("detect a credential canary crossing a chunk boundary")
        (base / "canary").unlink()
        changed = {**expected, f"{base.name}/empty": {"size": 1, "sha256": hashlib.sha256(b"x").hexdigest()}}
        rejected(lambda: make_archive(base, root / "mismatch.zip", expected=changed))
        checks.append("reject content that differs from the audited inventory")
        rejected(lambda: make_archive(base, base / "recursive.zip"))
        checks.append("refuse recursive inclusion of the archive itself")
        audit = root / "incomplete-audit"
        audit.mkdir()
        (audit / "summary.json").write_text(json.dumps({"groups": {"all": {"pairs": 19}}}))
        rejected(lambda: production(base, audit, root / "publication", False))
        assert not (root / "publication").exists()
        checks.append("refuse publication before all 65 pairs pass audit")
    return {"passed": True, "checks": checks, "count": len(checks), "model_api_calls": 0,
            "sample_sha256": {p.name: sha(p) for p in sample.iterdir() if p.is_file()}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sample", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = check(args.sample)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False))
