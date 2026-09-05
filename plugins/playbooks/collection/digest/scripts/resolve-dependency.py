#!/usr/bin/env python3
"""Resolve one name-qualified plugin dependency without pinning its version."""

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


def identifier_component(value: str, label: str) -> str:
    """Return an identifier that is safe to use as one path component."""
    component = os.path.basename(value)
    if component != value or not IDENTIFIER.fullmatch(component):
        fail("dependency-invalid", **{label: value}, reason="identity")
    return component


def resolved_descendant(root: Path, raw: str, plugin: str, source_kind: str) -> Path:
    """Resolve a manifest-declared path and keep it below its package root."""
    boundary = os.path.realpath(os.fspath(root))
    lexical = os.path.abspath(os.path.join(boundary, raw))
    candidate = os.path.realpath(lexical)
    if not candidate.startswith(boundary + os.sep):
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="path-escape")
    if candidate != lexical:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="path-symlink")
    if not os.path.isdir(candidate):
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="root-not-directory")
    return Path(candidate)


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
    source_kind: str,
    containment: Path | None = None,
    expected_directory_version: str | None = None,
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
    if not isinstance(data, dict) or data.get("name") != plugin:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-identity-mismatch")
    version = data.get("version")
    if not isinstance(version, str) or not SEMVER.fullmatch(version):
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-version-invalid")
    if expected_directory_version is not None and version != expected_directory_version:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="cache-version-mismatch")
    metadata = data.get("metadata", {})
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-metadata-invalid")
    harness = metadata.get("harness", {})
    if harness is None:
        harness = {}
    if not isinstance(harness, dict):
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-harness-metadata-invalid")
    entry_root = canonical
    entry_relative = harness.get("entryRoot")
    if entry_relative is not None:
        if (
            not isinstance(entry_relative, str)
            or not entry_relative.startswith("./")
            or Path(entry_relative).is_absolute()
            or ".." in Path(entry_relative).parts
        ):
            fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="entry-root-invalid")
        entry_root = resolved_descendant(canonical, entry_relative, plugin, source_kind)
        if not contained(canonical, entry_root):
            fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="entry-root-invalid")
    return {
        "plugin": plugin,
        "version": version,
        "runtime": runtime,
        "source_kind": source_kind,
        "root": str(entry_root),
        "package_root": str(canonical),
        "manifest": str(manifest),
    }


def dev_candidate(identity: str, runtime: str, plugin: str) -> dict[str, str] | None:
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
    return validate_candidate(Path(root), runtime, plugin, "dev-map")


def repository_candidate(plugin_root: Path, marketplace: str, runtime: str, plugin: str) -> dict[str, str] | None:
    rel_market = Path(".agents/plugins/marketplace.json") if runtime == "codex" else Path(".claude-plugin/marketplace.json")
    for ancestor in (plugin_root, *plugin_root.parents):
        bundle_manifest = manifest_path(ancestor, runtime)
        if bundle_manifest.is_file():
            bundle = load_json(bundle_manifest, "dependency-invalid")
            if isinstance(bundle, dict) and bundle.get("name") == marketplace:
                if plugin == marketplace:
                    return validate_candidate(ancestor, runtime, plugin, "repository", ancestor)
                internal = (
                    bundle.get("metadata", {})
                    .get("harness", {})
                    .get("internalPlugins", {})
                )
                relative = internal.get(plugin) if isinstance(internal, dict) else None
                if isinstance(relative, str):
                    candidate = resolved_descendant(ancestor, relative, plugin, "repository")
                    return validate_candidate(candidate, runtime, plugin, "repository", ancestor)
        manifest = ancestor / rel_market
        if not manifest.is_file():
            continue
        data = load_json(manifest, "dependency-invalid")
        if not isinstance(data, dict) or data.get("name") != marketplace:
            return None
        matches = [item for item in data.get("plugins", []) if isinstance(item, dict) and item.get("name") == plugin]
        if len(matches) > 1:
            fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="marketplace-entry")
        if len(matches) == 1:
            source = matches[0].get("source")
            if runtime == "codex":
                if not isinstance(source, dict) or source.get("source") != "local" or not isinstance(source.get("path"), str):
                    fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="source")
                relative = source["path"]
            else:
                if not isinstance(source, str):
                    fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="source")
                relative = source
        else:
            bundle_manifest = manifest_path(ancestor, runtime)
            bundle = load_json(bundle_manifest, "dependency-invalid")
            if not isinstance(bundle, dict) or bundle.get("name") != marketplace:
                fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="bundle-identity")
            internal = (
                bundle.get("metadata", {})
                .get("harness", {})
                .get("internalPlugins", {})
            )
            relative = internal.get(plugin) if isinstance(internal, dict) else None
            if not isinstance(relative, str):
                fail("dependency-invalid", plugin=plugin, marketplace=marketplace, source_kind="repository", reason="marketplace-entry")
        candidate = resolved_descendant(ancestor, relative, plugin, "repository")
        return validate_candidate(candidate, runtime, plugin, "repository", ancestor)
    return None


def semver_key(value: str) -> tuple[int, int, int, int, tuple[tuple[int, int | str], ...]] | None:
    matched = SEMVER.fullmatch(value)
    if matched is None:
        return None
    core_and_pre = value.split("+", 1)[0]
    core, separator, prerelease = core_and_pre.partition("-")
    major, minor, patch = (int(part) for part in core.split("."))
    if not separator:
        return major, minor, patch, 1, ()
    identifiers: list[tuple[int, int | str]] = []
    for part in prerelease.split("."):
        identifiers.append((0, int(part)) if part.isdigit() else (1, part))
    return major, minor, patch, 0, tuple(identifiers)


def selected_cache_root(runtime: str, plugin_root: Path, plugin: str) -> Path:
    override = os.environ.get("HARNESS_PLUGIN_CACHE_ROOT", "")
    if override:
        test_cache = plugin_root / ".harness-plugin-test-cache"
        if os.path.realpath(override) != os.path.realpath(test_cache):
            fail("dependency-invalid", plugin=plugin, source_kind="installed-cache", reason="test-cache-root-mismatch")
        return test_cache
    for ancestor in (plugin_root, *plugin_root.parents):
        if ancestor.name == "cache" and ancestor.parent.name == "plugins" and ancestor.is_dir():
            return ancestor
    fail("dependency-invalid", plugin=plugin, runtime=runtime, source_kind="installed-cache", reason="cache-root-unresolved")


def named_directory(parent: Path, expected: str) -> Path | None:
    if not parent.is_dir() or parent.is_symlink():
        return None
    matches = [child for child in parent.iterdir() if child.name == expected and child.is_dir() and not child.is_symlink()]
    if len(matches) > 1:
        fail("dependency-invalid", source_kind="installed-cache", reason="duplicate-cache-directory")
    return matches[0] if matches else None


def cache_candidate(marketplace: str, runtime: str, plugin: str, plugin_root: Path) -> dict[str, str] | None:
    cache = selected_cache_root(runtime, plugin_root, plugin)
    marketplace_cache = named_directory(cache, marketplace)
    if marketplace_cache is None:
        return None
    plugin_cache = named_directory(marketplace_cache, plugin)
    if plugin_cache is not None:
        candidates = [
            (key, child)
            for child in plugin_cache.iterdir()
            if child.is_dir() and (key := semver_key(child.name)) is not None
        ]
        if candidates:
            _, candidate = max(candidates, key=lambda item: (item[0], item[1].name))
            return validate_candidate(
                candidate,
                runtime,
                plugin,
                "installed-cache",
                cache,
                expected_directory_version=candidate.name,
            )

    # 内部pluginは、呼び出し元自身が同じpackage内にある場合だけ
    # repository_candidateで解決する。外部repositoryからcache内の内部実装を
    # 指定されても公開契約として扱わない。
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plugin-root", required=True)
    parser.add_argument("--plugin", required=True)
    parser.add_argument("--marketplace", required=True)
    args = parser.parse_args()
    plugin = identifier_component(args.plugin, "plugin")
    marketplace = identifier_component(args.marketplace, "marketplace")
    script_directory = Path(__file__).resolve().parent
    plugin_root = script_directory.parent if script_directory.name == "scripts" else script_directory
    if args.plugin_root != os.fspath(plugin_root):
        fail("dependency-invalid", plugin=plugin, marketplace=marketplace, reason="plugin-root-mismatch")
    runtime = runtime_for(plugin_root)
    identity = f"{marketplace}/{plugin}"
    candidate = dev_candidate(identity, runtime, plugin)
    if candidate is None:
        candidate = repository_candidate(plugin_root, marketplace, runtime, plugin)
    if candidate is None:
        candidate = cache_candidate(marketplace, runtime, plugin, plugin_root)
    if candidate is None:
        fail(
            "dependency-missing",
            plugin=plugin,
            marketplace=marketplace,
            runtime=runtime,
            install=f"{plugin}@{marketplace}",
        )
    candidate["marketplace"] = marketplace
    print(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
