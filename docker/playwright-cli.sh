#!/bin/bash
# Playwright CLI + browser + OS deps, all from the playwright-core bundled in
# @playwright/cli so revisions can't drift; PLAYWRIGHT_CLI_VERSION is the pin.
# Only chrome-headless-shell: full Chrome-for-Testing SIGTRAPs under this
# sandbox's security profile. The global config's browserName "chromium" (no
# channel) makes headless launches use the shell.
# The skill goes to ~/.agents/skills (opencode, Codex) and a local plugin via
# CLAUDE_CODE_PLUGIN_DIRS (Claude Code; ~/.claude/skills is a read-only mount).
# The browser is baked into /opt/playwright-seed because the named volume at
# PLAYWRIGHT_BROWSERS_PATH masks image content; entrypoint.sh syncs it in.
set -euo pipefail

npm install -g "@playwright/cli@${PLAYWRIGHT_CLI_VERSION}"
pkg="$(npm root -g)/@playwright/cli"

apt-get update
node "$pkg/node_modules/playwright-core/cli.js" install-deps chromium
rm -rf /var/lib/apt/lists/*

PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-seed \
    playwright-cli install-browser --only-shell chromium
chmod -R a+rX /opt/playwright-seed

plugin=/opt/claude-plugins/playwright-cli
mkdir -p "$plugin/.claude-plugin" "$plugin/skills" /home/dev/.agents/skills /home/dev/.playwright
cat > "$plugin/.claude-plugin/plugin.json" <<EOF
{"name": "playwright-cli", "version": "$PLAYWRIGHT_CLI_VERSION",
 "description": "Browser automation with playwright-cli"}
EOF
cp -r "$pkg/skills/playwright-cli" "$plugin/skills/"
cp -r "$pkg/skills/playwright-cli" /home/dev/.agents/skills/
echo '{"browser": {"browserName": "chromium"}}' > /home/dev/.playwright/cli.config.json
chmod -R a+rX /opt/claude-plugins
chown -R dev:dev /home/dev/.agents /home/dev/.playwright
