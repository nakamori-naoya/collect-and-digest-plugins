#!/usr/bin/env python3
"""Resolve one name-qualified plugin dependency without pinning its version."""

from __future__ import annotations

import argparse
import hashlib
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
    manifest = safe_path(canonical, str(manifest_path(canonical, runtime).relative_to(canonical)))
    if not manifest.is_file() or manifest.is_symlink():
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-missing")
    data = load_json(manifest, "dependency-invalid")
    if not isinstance(data, dict) or data.get("name") != plugin:
        fail("dependency-invalid", plugin=plugin, source_kind=source_kind, reason="manifest-identity-mismatch")
    version = data.get("version")
    if not isinstance(version, str) or semver_key(version) is None:
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
    contract = harness.get("contractVersion", 1)
    if type(contract) is not int or contract not in {1}:
        fail("dependency-incompatible", reason="contract-version", version=str(contract))
    skills = public_skills(canonical, data)
    return {
        "contract_version": contract,
        "content_hash": content_hash(canonical),
        "skills": skills,
        "prerelease_policy": "explicit-opt-in",
        "plugin": plugin,
        "version": version,
        "runtime": runtime,
        "source_kind": source_kind,
        "root": str(entry_root),
        "package_root": str(canonical),
        "manifest": str(manifest),
    }



def canonical_input_root(root: Path, label: str = "path-root") -> Path:
    """Validate persisted root identity without rebasing through new symlinks."""
    if not root.is_absolute() or any(path.is_symlink() for path in [root, *root.parents]):
        fail("dependency-invalid", reason=label + "-symlink")
    try:
        canonical = root.resolve(strict=True)
    except OSError as exc:
        fail("dependency-invalid", reason=label + "-unavailable", detail=str(exc))
    if canonical != root or not canonical.is_dir():
        fail("dependency-invalid", reason=label + "-noncanonical")
    return canonical


def safe_path(root: Path, raw: str, exists: bool = True) -> Path:
    if not isinstance(raw, str) or not raw or Path(raw).is_absolute() or ".." in Path(raw).parts or "\\" in raw:
        fail("dependency-invalid", reason="path-format", path=str(raw))
    boundary = canonical_input_root(root)
    lexical = Path(os.path.abspath(boundary / raw))
    if not contained(boundary, lexical):
        fail("dependency-invalid", reason="path-escape", path=raw)
    current = boundary
    for part in lexical.relative_to(boundary).parts:
        current /= part
        if current.is_symlink():
            fail("dependency-invalid", reason="path-symlink", path=raw)
    if exists and not lexical.exists():
        fail("dependency-invalid", reason="path-missing", path=raw)
    return lexical


def skill_name(path: Path) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        fail("dependency-invalid", reason="skill-frontmatter", path=str(path))
    header = lines[1:lines[1:].index("---") + 1]
    names = [line[6:].strip().strip("\"'") for line in header if line.startswith("name: ")]
    if len(names) != 1 or not IDENTIFIER.fullmatch(names[0]):
        fail("dependency-invalid", reason="skill-name", path=str(path))
    return names[0]


def public_skills(root: Path, data: dict) -> dict[str, str]:
    root = canonical_input_root(root)
    declared = data.get("skills")
    if declared is None:
        paths = [root / "SKILL.md"] if (root / "SKILL.md").is_file() else list((root / "skills").glob("*/SKILL.md"))
    else:
        if isinstance(declared, str):
            declared = [declared]
        if not isinstance(declared, list) or not declared:
            fail("dependency-invalid", reason="skills-schema")
        paths = []
        for raw in declared:
            member = safe_path(root, raw)
            candidates = [member / "SKILL.md"] if (member / "SKILL.md").exists() else list(member.glob("*/SKILL.md"))
            if not candidates:
                fail("dependency-invalid", reason="skill-entry-missing", path=str(member))
            paths.extend(candidates)
    result = {}
    for path in paths:
        path = safe_path(root, str(path.relative_to(root)))
        name = skill_name(path)
        if name in result:
            fail("dependency-invalid", reason="duplicate-skill", skill=name)
        result[name] = str(path)
    return result


def content_hash(root: Path) -> str:
    root = canonical_input_root(root)
    digest = hashlib.sha256()
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {".git", "__pycache__", ".harness-plugin-test-cache"})
        for name in sorted(dirs + files):
            path = Path(directory) / name
            if path.is_symlink():
                fail("dependency-invalid", reason="path-symlink", path=str(path))
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix == ".pyc":
                continue
            digest.update(str(path.relative_to(root)).encode() + b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return digest.hexdigest()


def check_steps(config: dict, selected: str | None = None) -> None:
    deps = config["deps"]
    available = {}
    for dep in deps.values():
        root = Path(dep.get("package_root", dep["root"]))
        root = canonical_input_root(root, "package-root")
        entry_root = canonical_input_root(Path(dep["root"]), "entry-root")
        if not contained(root, entry_root):
            fail("dependency-invalid", reason="entry-root-escape")
        # Inspect the lexical path before reading; hashing afterwards is too late.
        try:
            relative_manifest = Path(dep["manifest"]).relative_to(root)
        except ValueError:
            fail("dependency-invalid", reason="manifest-path-escape")
        checked_manifest = safe_path(root, str(relative_manifest))
        if not checked_manifest.is_file():
            fail("dependency-invalid", reason="manifest-not-file")
        manifest = load_json(checked_manifest, "dependency-invalid")
        if dep.get("content_hash") != content_hash(root):
            fail("dependency-changed", reason="content-hash", plugin=dep.get("plugin", "unknown"))
        contract = manifest.get("metadata", {}).get("harness", {}).get("contractVersion", 1)
        if type(contract) is not int or contract not in {1} or contract != dep.get("contract_version"):
            fail("dependency-incompatible", reason="contract-version")
        for name, path in public_skills(root, manifest).items():
            if name in available and available[name] != path:
                fail("dependency-invalid", reason="duplicate-skill", skill=name)
            available[name] = path
    matched = selected is None
    for step in config["playbook"]["steps"]:
        if selected == step["id"]:
            matched = True
        active = selected == step["id"] if selected else step.get("when") is None
        if "skill" in step:
            identifier_component(step["skill"], "skill")
            if active and step["skill"] not in available:
                print("[error] steps が指すスキルが requires のプラグインに無い: " + step["skill"], file=sys.stderr)
                raise SystemExit(2)
        if "script" in step:
            owner = step.get("plugin")
            if owner:
                identifier_component(owner, "plugin")
            base = Path(deps[owner]["root"]) if owner in deps else Path(config["playbook_root"])
            if owner and owner not in deps and active:
                fail("dependency-invalid", reason="script-owner-missing", plugin=owner)
            path = safe_path(base, step["script"], exists=active)
            if active and not path.is_file():
                fail("dependency-invalid", reason="script-not-file", path=str(path))
        if "playbook" in step:
            name = identifier_component(step["playbook"], "playbook")
            if active:
                if name not in deps:
                    fail("dependency-invalid", reason="playbook-owner-missing", plugin=name)
                base = Path(deps[name]["root"])
                safe_path(base, "playbook.yml")
                safe_path(base, "scripts/resolve.sh")
    if not matched:
        fail("dependency-invalid", reason="unknown-step", step=str(selected))

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
        if part.isdigit() and len(part) > 1 and part.startswith("0"):
            return None
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
            if child.is_dir() and not child.is_symlink() and (key := semver_key(child.name)) is not None
            and (key[3] == 1 or os.environ.get("HARNESS_PLUGIN_ALLOW_PRERELEASE") == "1")
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
    if len(sys.argv) > 1 and sys.argv[1] == "--check-steps":
        config = json.load(sys.stdin)
        check_steps(config, sys.argv[2] if len(sys.argv) == 3 else None)
        return 0
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
