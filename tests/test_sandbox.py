"""Regression checks using synthetic credentials; no Docker daemon or API calls."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("prepare_auth", ROOT / "prepare-auth.py")
auth = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auth)
LOGIN = {
    "auth_mode": "chatgpt",
    "OPENAI_API_KEY": "stored-api-secret",
    "tokens": {
        "access_token": "oauth-access",
        "refresh_token": "oauth-refresh",
        "id_token": "oauth-id",
        "account_id": "account",
    },
    "last_refresh": "2026-09-21T00:00:00Z",
}


class AuthTests(unittest.TestCase):
    def test_codex_oauth_survives_without_api_key(self):
        result = auth.filter_auth("codex", LOGIN)
        self.assertEqual(result["tokens"], LOGIN["tokens"])
        self.assertEqual(result["last_refresh"], LOGIN["last_refresh"])
        self.assertNotIn("OPENAI_API_KEY", result)

    def test_codex_api_only_and_invalid_data_are_not_forwarded(self):
        for data in ({"OPENAI_API_KEY": "secret"}, [], None, {"tokens": "invalid"}):
            self.assertEqual(auth.filter_auth("codex", data), {})

    def test_explicit_api_key_opt_in(self):
        self.assertEqual(auth.filter_auth("codex", LOGIN, True), LOGIN)

    def test_other_agents_exclude_keys(self):
        self.assertEqual(auth.filter_auth("claude", {
            "claudeAiOauth": {"accessToken": "oauth"}, "primaryApiKey": "secret"
        }), {"claudeAiOauth": {"accessToken": "oauth"}})
        self.assertEqual(auth.filter_auth("opencode", {
            "anthropic": {"type": "oauth", "access": "oauth"},
            "openai": {"type": "api", "key": "secret"},
        }), {"anthropic": {"type": "oauth", "access": "oauth"}})

    def test_config_filters_nested_api_keys(self):
        self.assertEqual(auth.filter_auth("config", {
            "model": "local/model",
            "provider": {"local": {"options": {"apiKey": "secret", "baseURL": "url"}}},
            "mcpServers": {"test": {"env": {"ANTHROPIC_API_KEY": "secret"}}},
        }), {
            "model": "local/model",
            "provider": {"local": {"options": {"baseURL": "url"}}},
            "mcpServers": {"test": {"env": {}}},
        })


class SandboxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.host = self.base / "host with spaces"
        self.host.mkdir()
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.env = {
            **os.environ,
            "HOME": str(self.host),
            "CODEX_HOME": str(self.host / "custom codex"),
            "XDG_CACHE_HOME": str(self.base / "cache"),
            "TMPDIR": str(self.base),
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "CLAUDE_SANDBOX_MODE": "rootful",
            "ANTHROPIC_API_KEY": "environment-anthropic-secret",
            "OPENAI_API_KEY": "environment-openai-secret",
            "CAPTURE": str(self.base / "capture.json"),
        }
        self.write(self.host / "custom codex/auth.json", LOGIN)
        self.write(self.host / ".claude/.credentials.json", {
            "claudeAiOauth": {"accessToken": "claude-oauth"}, "primaryApiKey": "secret"
        })
        self.write(self.host / ".claude.json", {"primaryApiKey": "secret"})
        self.write(self.host / ".local/share/opencode/auth.json", {
            "openai": {"type": "api", "key": "secret"},
            "anthropic": {"type": "oauth", "access": "opencode-oauth"},
        })
        self.write(self.host / ".config/opencode/opencode.json", {
            "provider": {"openai": {"options": {"apiKey": "secret"}}}
        })
        self.executable("docker", '''#!/usr/bin/env python3
import json, os, pathlib, sys
if "run" in sys.argv:
    names = ["CLAUDE_CREDENTIALS_FILE", "CLAUDE_CONFIG_FILE", "OPENCODE_AUTH_FILE",
             "OPENCODE_CONFIG_FILE", "CODEX_AUTH_FILE"]
    paths = {key: os.environ[key] for key in names}
    data = {"args": sys.argv[1:], "paths": paths,
            "files": {key: pathlib.Path(path).read_text() for key, path in paths.items()},
            "modes": {key: pathlib.Path(path).stat().st_mode & 0o777 for key, path in paths.items()},
            "env": dict(os.environ)}
    pathlib.Path(os.environ["CAPTURE"]).write_text(json.dumps(data))
''')

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def executable(self, name, contents):
        path = self.bin / name
        path.write_text(contents)
        path.chmod(0o755)

    def launch(self, *args, success=True):
        result = subprocess.run([str(ROOT / "claude-sandbox"), *args, str(self.host)],
                                env=self.env, capture_output=True, text=True)
        if not success:
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(Path(self.env["CAPTURE"]).exists())
            return result
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        return json.loads(Path(self.env["CAPTURE"]).read_text())

    def test_codex_launch_private_staging_and_cleanup(self):
        data = self.launch("--codex")
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", data["args"])
        self.assertEqual(data["env"]["SANDBOX_AGENT"], "codex")
        self.assertEqual(data["env"]["SANDBOX_ANTHROPIC_API_KEY"], "")
        self.assertEqual(data["env"]["SANDBOX_OPENAI_API_KEY"], "")
        self.assertEqual(json.loads(data["files"]["CODEX_AUTH_FILE"])["tokens"], LOGIN["tokens"])
        self.assertNotIn("stored-api-secret", str(data["files"]))
        self.assertEqual(data["files"]["CLAUDE_CREDENTIALS_FILE"], "")
        self.assertEqual(data["files"]["OPENCODE_AUTH_FILE"], "")
        self.assertTrue(all(mode == 0o600 for mode in data["modes"].values()))
        self.assertTrue(all(not Path(path).exists() for path in data["paths"].values()))
        self.assertEqual(json.loads((self.host / "custom codex/auth.json").read_text()), LOGIN)

    def test_default_codex_home(self):
        del self.env["CODEX_HOME"]
        self.write(self.host / ".codex/auth.json", LOGIN)
        data = self.launch("--codex")
        self.assertIn("oauth-access", data["files"]["CODEX_AUTH_FILE"])

    def test_api_keys_require_opt_in(self):
        data = self.launch("--codex", "--api-keys")
        self.assertEqual(json.loads(data["files"]["CODEX_AUTH_FILE"]), LOGIN)
        self.assertEqual(data["env"]["SANDBOX_OPENAI_API_KEY"], "environment-openai-secret")

    def test_missing_malformed_and_api_only_codex_login(self):
        path = self.host / "custom codex/auth.json"
        for contents in (None, "{bad json", '{"OPENAI_API_KEY": "secret"}'):
            with self.subTest(contents=contents):
                if contents is None:
                    path.unlink()
                else:
                    path.write_text(contents)
                self.assertEqual(self.launch("--codex")["files"]["CODEX_AUTH_FILE"], "")

    def test_conflicting_options(self):
        for args in (("--codex", "--opencode"), ("--codex", "--agents"),
                     ("--codex", "--port", "8080"), ("--codex", "--gpu", "--rust")):
            with self.subTest(args=args):
                self.launch(*args, success=False)

    def test_claude_and_opencode_defaults(self):
        for args, agent in (((), "claude"), (("--agents",), "claude"), (("--opencode",), "opencode")):
            with self.subTest(agent=agent, args=args):
                data = self.launch(*args)
                self.assertEqual(data["env"]["SANDBOX_AGENT"], agent)
                self.assertNotIn("secret", str(data["files"]))
                self.assertEqual(data["files"]["CODEX_AUTH_FILE"], "")

    def test_legacy_claude_key_is_opt_in(self):
        (self.host / ".claude/.credentials.json").unlink()
        self.write(self.host / ".claude/config.json", {"primaryApiKey": "legacy-secret"})
        self.env["ANTHROPIC_API_KEY"] = ""
        self.launch(success=False)
        data = self.launch("--api-keys")
        self.assertEqual(data["env"]["SANDBOX_ANTHROPIC_API_KEY"], "legacy-secret")

    def test_macos_claude_keychain_login(self):
        self.executable("uname", "#!/bin/bash\necho Darwin\n")
        self.executable("security", '''#!/bin/bash
echo '{"claudeAiOauth":{"accessToken":"keychain-oauth"},"primaryApiKey":"secret"}'
''')
        data = self.launch()
        self.assertEqual(json.loads(data["files"]["CLAUDE_CREDENTIALS_FILE"]), {
            "claudeAiOauth": {"accessToken": "keychain-oauth"}
        })
        self.assertFalse(list(self.base.glob("claude-sandbox-auth.*")))

    @unittest.skipUnless(shutil.which("docker"), "Docker Compose is not installed")
    def test_rendered_compose_all_images_and_modes(self):
        docker = shutil.which("docker")
        for mode in ("rootful", "rootless"):
            self.env["CLAUDE_SANDBOX_MODE"] = mode
            for image in ((), ("--gpu",), ("--rust",)):
                with self.subTest(mode=mode, image=image):
                    data = self.launch("--codex", *image)
                    args = data["args"][:data["args"].index("run")]
                    result = subprocess.run([docker, *args, "config", "--format", "json"],
                                            env=data["env"], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    service = json.loads(result.stdout)["services"]["claude-dev"]
                    self.assertEqual(service["environment"]["OPENAI_API_KEY"], "")
                    self.assertEqual(service["environment"]["ANTHROPIC_API_KEY"], "")
                    self.assertEqual(service["environment"]["CODEX_HOME"], "/home/dev/.codex")
                    mounts = {m["target"]: m for m in service["volumes"]}
                    self.assertTrue(mounts["/tmp/host-codex-auth.json"]["read_only"])
                    self.assertEqual(mounts["/home/dev/.codex"]["type"], "volume")

    def run_entrypoint(self, host_login, persisted=None, api_keys="false"):
        sandbox = self.base / "container"
        sandbox.mkdir(exist_ok=True)
        for directory in ("home/dev/.codex", "run/user", "tmp", "etc"):
            (sandbox / directory).mkdir(parents=True, exist_ok=True)
        if host_login is not None:
            self.write(sandbox / "tmp/host-codex-auth.json", host_login)
        if persisted is not None:
            self.write(sandbox / "home/dev/.codex/auth.json", persisted)
        for command in ("chown", "setfacl", "playwright-mcp"):
            self.executable(command, "#!/bin/bash\nexit 0\n")
        self.executable("gosu", '#!/bin/bash\nprintf "%s\\n" "$*" >> "$GOSU_LOG"\n')
        script = (ROOT / "entrypoint.sh").read_text()
        for prefix in ("/home/dev", "/opt/", "/workspace/", "/tmp/host-", "/run/user", "/etc/asound.conf"):
            script = script.replace(prefix, str(sandbox) + prefix)
        script = script.replace("/usr/local/lib/claude-sandbox/prepare-auth.py", str(ROOT / "prepare-auth.py"))
        result = subprocess.run(["bash", "-c", script, "entrypoint", "codex", "--dangerously-bypass-approvals-and-sandbox"],
                                env={**self.env, "SANDBOX_AGENT": "codex", "SANDBOX_API_KEYS": api_keys,
                                     "CLAUDE_SANDBOX_NO_PLAYWRIGHT": "", "CLAUDE_SANDBOX_NO_MPS": "1",
                                     "GOSU_LOG": str(self.base / "gosu.log")},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return sandbox / "home/dev/.codex/auth.json"

    def test_entrypoint_copies_login_and_registers_codex_mcp(self):
        path = self.run_entrypoint(auth.filter_auth("codex", LOGIN))
        self.assertEqual(json.loads(path.read_text())["tokens"], LOGIN["tokens"])
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        calls = (self.base / "gosu.log").read_text()
        self.assertIn("codex mcp add playwright -- playwright-mcp", calls)
        self.assertNotIn("claude mcp", calls)
        self.assertIn("dev codex --dangerously-bypass-approvals-and-sandbox", calls)

    def test_entrypoint_keeps_sandbox_login_without_host_login(self):
        path = self.run_entrypoint(None, persisted=LOGIN)
        self.assertEqual(json.loads(path.read_text())["tokens"], LOGIN["tokens"])
        self.assertNotIn("OPENAI_API_KEY", json.loads(path.read_text()))

    def test_entrypoint_removes_old_api_only_auth_without_opt_in(self):
        path = self.run_entrypoint(None, persisted={"OPENAI_API_KEY": "secret"})
        self.assertFalse(path.exists())

    def test_entrypoint_api_key_login_requires_opt_in(self):
        self.run_entrypoint(LOGIN, api_keys="true")
        calls = (self.base / "gosu.log").read_text()
        self.assertIn('codex -c cli_auth_credentials_store="file" login --with-api-key', calls)
        self.assertNotIn("environment-openai-secret", calls)


if __name__ == "__main__":
    unittest.main()
