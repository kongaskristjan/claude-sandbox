#!/usr/bin/env python3
"""Stage host authentication without exposing API keys in Docker bind mounts."""

import json
import os
from pathlib import Path
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


def main():
    kind, source, destination, allow = sys.argv[1:]
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
