#!/usr/bin/env python3
"""Validate and deterministically package the think3 runtime; PyYAML is dev-only."""

import argparse
import ast
import hashlib
import io
import json
from pathlib import Path
import re
import sys
import zipfile

import yaml


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "think3"
EXPECTED_FILES = {
    "SKILL.md", "agents/openai.yaml", "references/cross-project-review.md",
    "references/tracker.md", "references/version-history.md",
    "references/expression.md", "scripts/tracker.py",
}
ORIGINAL_SHA256 = "e21078de9c246b36fc4767aba10a43dc79963090ee85eb71a838920bdef4530a"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate():
    files = sorted((path for path in SKILL.rglob("*") if path.is_file()),
                   key=lambda path: path.relative_to(SKILL).as_posix())
    require({path.relative_to(SKILL).as_posix() for path in files} == EXPECTED_FILES,
            "Runtime inventory differs from the release allowlist; check for missing files or accidental data.")
    for path in files:
        require(not path.is_symlink(), f"Release cannot contain symlink: {path}")
        path.read_text(encoding="utf-8")
    body = (SKILL / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", body, re.S)
    require(match is not None, "Missing SKILL.md YAML frontmatter")
    front = yaml.safe_load(match.group(1))
    require(front.get("name") == "think3", "Unexpected skill name")
    require(isinstance(front.get("description"), str) and front["description"].strip(), "Missing description")
    version = str(front.get("metadata", {}).get("version", ""))
    require(re.fullmatch(r"\d+\.\d+\.\d+", version), "Version must be major.minor.patch")
    history = (SKILL / "references/version-history.md").read_text(encoding="utf-8")
    require(f"## {version}\n" in history, "Current version missing from version history")
    config = yaml.safe_load((SKILL / "agents/openai.yaml").read_text(encoding="utf-8"))
    require(config.get("policy", {}).get("allow_implicit_invocation") is True, "Automatic invocation policy is missing")
    interface = config.get("interface", {})
    require(interface.get("display_name") == "吾日三省吾身", "Display name changed")
    require(25 <= len(interface.get("short_description", "")) <= 64, "UI short description must be 25-64 characters")
    require("$think3" in interface.get("default_prompt", ""), "Default prompt must name $think3")
    links = []
    for path in files:
        if path.suffix == ".md":
            for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in target or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#", 1)[0]).resolve()
                require(resolved.is_relative_to(SKILL.resolve()) and resolved.is_file(), f"Broken/escaping runtime link: {target}")
                links.append({"source": path.relative_to(SKILL).as_posix(), "target": target})
    tree = ast.parse((SKILL / "scripts/tracker.py").read_text(encoding="utf-8"), feature_version=(3, 10))
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    require(imports <= sys.stdlib_module_names, "Runtime requires third-party Python dependencies")
    original = (ROOT / "upstream/think3-1.0.0-original.zip").read_bytes()
    require(sha(original) == ORIGINAL_SHA256, "Original baseline archive changed")
    with zipfile.ZipFile(io.BytesIO(original)) as archive:
        require(archive.testzip() is None, "Original archive failed CRC")
        original_entry_bytes = len(archive.read("think3/SKILL.md"))
    return version, files, {
        "version": version, "checks": "passed", "runtime_files": len(files),
        "allow_implicit_invocation": True, "runtime_imports": sorted(imports),
        "links": links, "upstream_sha256": ORIGINAL_SHA256,
        "entrypoint_bytes": (SKILL / "SKILL.md").stat().st_size,
        "original_entrypoint_bytes": original_entry_bytes,
        "files": [{"path": path.relative_to(SKILL).as_posix(), "bytes": path.stat().st_size,
                   "sha256": sha(path.read_bytes())} for path in files],
    }


def build(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            name = "think3/" + path.relative_to(SKILL).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    payload = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        require(archive.testzip() is None, "Release archive failed CRC")
        for path in files:
            name = "think3/" + path.relative_to(SKILL).as_posix()
            require(archive.read(name) == path.read_bytes(), f"Archive mismatch: {name}")
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Validate only; do not write files")
    parser.add_argument("--replace-draft", action="store_true", help="Replace an existing, different local draft archive")
    args = parser.parse_args()
    try:
        version, files, report = validate()
        if not args.check:
            payload = build(files)
            require(payload == build(files), "Repeated builds differ")
            target = ROOT / "releases" / f"吾日三省吾身_think3_{version}.zip"
            require(not target.exists() or target.read_bytes() == payload or args.replace_draft,
                    "A different archive already exists. Use --replace-draft only for an unpublished draft.")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            report["archive"] = {"path": target.relative_to(ROOT).as_posix(), "bytes": len(payload),
                                 "sha256": sha(payload), "crc": "passed", "roundtrip": "passed", "reproducible": True}
            (ROOT / "validation").mkdir(exist_ok=True)
            (ROOT / "validation/release-manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, SyntaxError, yaml.YAMLError, zipfile.BadZipFile) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
