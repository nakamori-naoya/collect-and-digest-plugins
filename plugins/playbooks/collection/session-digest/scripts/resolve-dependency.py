#!/usr/bin/env python3
"""Resolve one qualified plugin dependency without scanning unrelated marketplaces."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys


IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*$")
SEMVER = re.compile(
    r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?"
    r"(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)


def fail(code: str, **fields: str) -> None:
    detail = " ".join(f"{key}={value}" for key, value in fields.items())
    print(f"[error:{code}] {detail}".rstrip(), file=sys.stderr)
    raise SystemExit(2)


def load_json(path: Path, code: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(code, path=str(path), reason=str(exc))


def contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def runtime_for(plugin_root: Path) -> str:
    explicit = os.environ.get("HARNESS_PLUGIN_RUNTIME", "")
    if explicit:
        if explicit not in {"claude", "codex"}:
            fail("dependency-runtime-unresolved", runtime=explicit)
        return explicit
    if os.environ.get("CLAUDE_PLUGIN_ROOT"):
        return "claude"
    if os.environ.get("CODEX_HOME"):
        return "codex"
    candidates = {
        "claude": Path(os.environ.get("CLAUDE_PLUGIN_CACHE", Path.home() / ".claude/plugins/cache")),
        "codex": Path(os.environ.get("CODEX_PLUGIN_CACHE", Path.home() / ".codex/plugins/cache")),
    }
    resolved = plugin_root.resolve()
    detected = [name for name, root in candidates.items() if root.exists() and contained(root.resolve(), resolved)]
    if len(detected) == 1:
        return detected[0]
    fail("dependency-runtime-unresolved", plugin_root=str(plugin_root))


def manifest_path(root: Path, runtime: str) -> Path:
    directory = ".codex-plugin" if runtime == "codex" else ".claude-plugin"
    return root / directory / "plugin.json"


def validate_candidate(
    root: Path,
    runtime: str,
    plugin: str,
    version: str,
    source_kind: str,
    containment: Path | None = None,
) -> dict[str, str]:
    try:
        canonical = root.resolve(strict=True)
    except OSError as exc:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason=str(exc))
    if not canonical.is_dir():
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="root-not-directory")
    if containment is not None:
        boundary = containment.resolve(strict=True)
        if not contained(boundary, canonical):
            fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="path-escape")
    manifest = manifest_path(canonical, runtime)
    if not manifest.is_file() or manifest.is_symlink():
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-missing")
    data = load_json(manifest, "dependency-invalid")
    if not isinstance(data, dict) or data.get("name") != plugin or data.get("version") != version:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-identity-mismatch")
    return {
        "plugin": plugin,
        "version": version,
        "runtime": runtime,
        "source_kind": source_kind,
        "root": str(canonical),
        "manifest": str(manifest),
    }


def dev_candidate(identity: str, runtime: str, plugin: str, version: str) -> dict[str, str] | None:
    raw = os.environ.get("HARNESS_PLUGIN_DEV_ROOTS", "")
    if not raw:
        return None
    path = Path(raw)
    data = load_json(path, "dependency-invalid")
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("dependencies"), dict):
        fail("dependency-invalid", plugin=plugin, source_kind="dev-map", reason="schema")
    root = data["dependencies"].get(identity)
    if root is None:
        return None
    if not isinstance(root, str) or not Path(root).is_absolute():
        fail("dependency-invalid", plugin=plugin, source_kind="dev-map", reason="root-must-be-absolute")
    return validate_candidate(Path(root), runtime, plugin, version, "dev-map")


def repository_candidate(
    plugin_root: Path, marketplace: str, runtime: str, plugin: str, version: str
) -> dict[str, str] | None:
    rel_market = Path(".agents/plugins/marketplace.json") if runtime == "codex" else Path(".claude-plugin/marketplace.json")
    for ancestor in (plugin_root, *plugin_root.parents):
        manifest = ancestor / rel_market
        if not manifest.is_file():
            continue
        data = load_json(manifest, "dependency-invalid")
        if not isinstance(data, dict) or data.get("name") != marketplace:
            return None
        matches = [item for item in data.get("plugins", []) if isinstance(item, dict) and item.get("name") == plugin]
        if len(matches) != 1 or matches[0].get("version") != version:
            fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="marketplace-entry")
        source = matches[0].get("source")
        if runtime == "codex":
            if not isinstance(source, dict) or source.get("source") != "local" or not isinstance(source.get("path"), str):
                fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="source")
            relative = source["path"]
        else:
            if not isinstance(source, str):
                fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="source")
            relative = source
        return validate_candidate(ancestor / relative, runtime, plugin, version, "repository", ancestor)
    return None


def cache_candidate(marketplace: str, runtime: str, plugin: str, version: str) -> dict[str, str] | None:
    override = os.environ.get("HARNESS_PLUGIN_CACHE_ROOT", "")
    if override:
        cache = Path(override)
    elif runtime == "codex":
        cache = Path(os.environ.get("CODEX_PLUGIN_CACHE", Path.home() / ".codex/plugins/cache"))
    else:
        cache = Path(os.environ.get("CLAUDE_PLUGIN_CACHE", Path.home() / ".claude/plugins/cache"))
    candidate = cache / marketplace / plugin / version
    if not candidate.exists():
        return None
    return validate_candidate(candidate, runtime, plugin, version, "installed-cache", cache)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--marketplace", required=True)
    parser.add_argument("--version", required=True)
    args = parser.parse_args()
    if not IDENTIFIER.fullmatch(args.plugin) or not IDENTIFIER.fullmatch(args.marketplace) or not SEMVER.fullmatch(args.version):
        fail("dependency-invalid", plugin=args.plugin, marketplace=args.marketplace, version=args.version, reason="identity")
    plugin_root = Path(args.plugin_root).resolve(strict=True)
    runtime = runtime_for(plugin_root)
    identity = f"{args.marketplace}/{args.plugin}/{args.version}"
    candidate = dev_candidate(identity, runtime, args.plugin, args.version)
    if candidate is None:
        candidate = repository_candidate(plugin_root, args.marketplace, runtime, args.plugin, args.version)
    if candidate is None:
        candidate = cache_candidate(args.marketplace, runtime, args.plugin, args.version)
    if candidate is None:
        fail(
            "dependency-missing",
            plugin=args.plugin,
            marketplace=args.marketplace,
            version=args.version,
            runtime=runtime,
            install=f"{args.plugin}@{args.marketplace}",
        )
    candidate["marketplace"] = args.marketplace
    print(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
