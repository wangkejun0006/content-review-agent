"""Allowlisted public export; never inspect credentials or private runtime."""

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def selected_files(root=ROOT):
    config = json.loads((root / "release/manifest.json").read_text())
    paths = {root / n for n in config["files"]}
    for name in config["directories"]:
        paths.update(f for f in (root / name).rglob("*") if f.is_file() or f.is_symlink())
    selected = []
    for path in sorted(paths):
        rel = path.relative_to(root)
        if any(
            x in config["excluded_parts"] or x.endswith((".egg-info", ".dist-info"))
            for x in rel.parts
        ):
            continue
        if (
            path.name.startswith(".env")
            or path.name in config["excluded_names"]
            or path.suffix in config["excluded_suffixes"]
        ):
            continue
        if any((root / Path(*rel.parts[:i])).is_symlink() for i in range(1, len(rel.parts) + 1)):
            raise ValueError("symlink_in_public_source:" + str(rel))
        if not path.is_file() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("missing_or_external_public_source:" + str(rel))
        selected.append(path)
    return selected


def audit(files):
    findings = []
    for p in files:
        raw = p.read_bytes()
        for pattern in [
            rb"\b(?:sk-|gh[pousr]_|github_pat_)[A-Za-z0-9_-]{24,}",
            rb"\bAKIA[A-Z0-9]{16}\b",
            rb"-----BEGIN [^\n]*PRIVATE KEY-----\s*\n[A-Za-z0-9+/=]{24,}",
        ]:
            if re.search(pattern, raw):
                findings.append({"file": p.name, "kind": "credential_pattern"})
    return findings


def export(destination):
    files = selected_files()
    if audit(files):
        raise ValueError("credential_pattern_requires_private_review")
    if destination.exists():
        raise ValueError("fresh_export_directory_required")
    destination.mkdir(parents=True)
    manifest = []
    for source in files:
        rel = source.relative_to(ROOT)
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        manifest.append(
            {"path": rel.as_posix(), "sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        )
    (destination / "release-export.json").write_text(
        json.dumps({"schema": "paper-orbit.export/1", "files": manifest}, indent=2) + "\n"
    )
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps({"status": "exported_locally", "files": len(export(args.output))}))
