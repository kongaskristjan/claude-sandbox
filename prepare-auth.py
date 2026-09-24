#!/usr/bin/env python3
"""Stage host authentication and Codex setup before Docker can access them."""

import json
import os
from pathlib import Path
import shutil
import sys


def without_api_keys(value):
    if isinstance(value, dict):
        return {
            key: without_api_keys(item)
            for key, item in value.items()
            if not key.lower().replace("_", "").replace("-", "").endswith(
                ("apikey", "apikeys")
            )
        }
    if isinstance(value, list):
        return [without_api_keys(item) for item in value]
    return value


def filter_auth(kind, data, allow_api_keys=False):
    if not isinstance(data, dict):
        return {}
    if allow_api_keys:
        return data
    if kind == "codex":
        tokens = data.get("tokens")
        if not isinstance(tokens, dict) or not tokens.get("access_token"):
            return {}
        # Reconstruct the ChatGPT login instead of copying API-key auth modes
        # or unknown fields from auth.json.
        result = {
            "auth_mode": "chatgpt",
            "tokens": {key: tokens[key] for key in (
                "id_token", "access_token", "refresh_token", "account_id"
            ) if key in tokens},
        }
        if "last_refresh" in data:
            result["last_refresh"] = data["last_refresh"]
        return result
    if kind == "claude":
        oauth = data.get("claudeAiOauth")
        return {"claudeAiOauth": without_api_keys(oauth)} if isinstance(oauth, dict) else {}
    if kind == "opencode":
        return {
            provider: without_api_keys(auth)
            for provider, auth in data.items()
            if isinstance(auth, dict) and auth.get("type") == "oauth"
        }
    return without_api_keys(data)


def stage_codex_config(source, destination, allow_api_keys=False):
    # Parse TOML rather than filtering lines: keys can be quoted, nested, or
    # stored in inline tables and multiline strings. Keep the original text
    # (including comments) when no filtering is needed.
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            raise SystemExit(
                "Copying Codex config requires tomli on Python older than 3.11. "
                "Install it with: python3 -m pip install tomli"
            ) from None
    contents = source.read_text()
    data = tomllib.loads(contents)
    filtered = data if allow_api_keys else without_api_keys(data)
    if not allow_api_keys:
        # Codex custom providers also accept a literal bearer credential.
        def remove_bearer(value):
            if isinstance(value, dict):
                return {key: remove_bearer(item) for key, item in value.items()
                        if key != "experimental_bearer_token"}
            if isinstance(value, list):
                return [remove_bearer(item) for item in value]
            return value
        filtered = remove_bearer(filtered)
    if filtered != data:
        def toml_value(value):
            if isinstance(value, dict):
                return "{ " + ", ".join(
                    f"{json.dumps(key, ensure_ascii=False)} = {toml_value(item)}"
                    for key, item in value.items()) + " }"
            if isinstance(value, list):
                return "[" + ", ".join(map(toml_value, value)) + "]"
            if isinstance(value, (str, bool, int, float)):
                return json.dumps(value, ensure_ascii=False) if not isinstance(value, float) else repr(value)
            return value.isoformat()  # TOML dates and times
        contents = "".join(f"{json.dumps(key, ensure_ascii=False)} = {toml_value(value)}\n"
                           for key, value in filtered.items())
    destination.write_text(contents)
    destination.chmod(0o600)


def stage_codex_setup(source, destination, allow_api_keys=False):
    """Copy portable setup, excluding auth, session history, logs, and caches."""
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not source.is_dir():
        return
    for path in source.iterdir():
        target = destination / path.name
        if path.is_file() and (path.suffix == ".toml" or path.name in (
                "AGENTS.md", "AGENTS.override.md", "instructions.md")):
            if path.suffix == ".toml":
                stage_codex_config(path, target, allow_api_keys)
            else:
                shutil.copyfile(path, target)
                target.chmod(0o600)
        elif path.is_dir() and path.name in ("agents", "skills", "rules", "prompts"):
            # Dereference links so host-linked skills work without mounting
            # their original host paths. Preserve executable helper scripts.
            shutil.copytree(path, target, dirs_exist_ok=True)
            if path.name == "agents":
                for config in target.rglob("*.toml"):
                    stage_codex_config(config, config, allow_api_keys)


def main():
    kind, source, destination, allow = sys.argv[1:]
    if kind == "codex-setup":
        stage_codex_setup(Path(source), Path(destination), allow == "true")
        return
    if kind == "codex-config":
        stage_codex_config(Path(source), Path(destination), allow == "true")
        return
    try:
        data = json.loads(Path(source).read_text())
    except FileNotFoundError:
        data = {}
    except (OSError, ValueError):
        print(f"Warning: could not read {kind} JSON; skipping host credentials/config.", file=sys.stderr)
        data = {}
    data = filter_auth(kind, data, allow == "true")
    # Empty files mean no host login; the entrypoint can retain a sandbox login.
    with open(destination, "w", opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
        if data:
            json.dump(data, stream)


if __name__ == "__main__":
    main()
