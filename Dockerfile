FROM ubuntu:24.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    git git-lfs curl wget sudo gosu acl \
    build-essential cmake \
    sox libsox-fmt-all alsa-utils pulseaudio-utils libasound2-plugins \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash -G root,audio dev

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/ \
    && cp /root/.local/bin/uvx /usr/local/bin/

# Playwright CLI + browser + OS deps, all from the playwright-core bundled in
# @playwright/cli so revisions can't drift; PLAYWRIGHT_CLI_VERSION is the pin.
# Only chrome-headless-shell: full Chrome-for-Testing SIGTRAPs under this
# sandbox's security profile. The global config's browserName "chromium" (no
# channel) makes headless launches use the shell.
# The skill goes to ~/.agents/skills (opencode, Codex) and a local plugin via
# CLAUDE_CODE_PLUGIN_DIRS (Claude Code; ~/.claude/skills is a read-only mount).
# The browser is baked into /opt/playwright-seed because the named volume at
# PLAYWRIGHT_BROWSERS_PATH masks image content; entrypoint.sh syncs it in.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    PLAYWRIGHT_CLI_VERSION=0.1.21 \
    CLAUDE_CODE_PLUGIN_DIRS=/opt/claude-plugins/playwright-cli \
    NO_UPDATE_NOTIFIER=1
RUN npm install -g @playwright/cli@${PLAYWRIGHT_CLI_VERSION} \
    && apt-get update \
    && node "$(npm root -g)/@playwright/cli/node_modules/playwright-core/cli.js" \
        install-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-seed \
        playwright-cli install-browser --only-shell chromium \
    && chmod -R a+rX /opt/playwright-seed \
    && skill="$(npm root -g)/@playwright/cli/skills/playwright-cli" \
    && mkdir -p /opt/claude-plugins/playwright-cli/.claude-plugin \
        /opt/claude-plugins/playwright-cli/skills /home/dev/.agents/skills \
        /home/dev/.playwright \
    && printf '%s\n' '{"name": "playwright-cli", "version": "'"$PLAYWRIGHT_CLI_VERSION"'",' \
        ' "description": "Browser automation with playwright-cli"}' \
        > /opt/claude-plugins/playwright-cli/.claude-plugin/plugin.json \
    && cp -r "$skill" /opt/claude-plugins/playwright-cli/skills/ \
    && cp -r "$skill" /home/dev/.agents/skills/ \
    && echo '{"browser": {"browserName": "chromium"}}' \
        > /home/dev/.playwright/cli.config.json \
    && chmod -R a+rX /opt/claude-plugins \
    && chown -R dev:dev /home/dev/.agents /home/dev/.playwright

# Install Claude Code as native binary (has built-in audio for voice mode).
# This layer sits after every other install so that invalidating it is cheap:
# `claude-sandbox --update` changes CLAUDE_CACHE_BUST, which re-runs this RUN
# (and the layers below it) while apt, node, uv and the Playwright browser
# stay cached. The value is persisted on the host and passed on every build,
# so later runs keep hitting the refreshed layer instead of the stale one.
ARG CLAUDE_CACHE_BUST=0
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && cp /root/.local/share/claude/versions/* /usr/local/bin/claude

# Install opencode alongside Claude Code. It is a standalone native binary,
# copied to /usr/local/bin so the non-root dev user can run it. The agent is
# chosen at runtime (SANDBOX_AGENT), not by which image is built, so it is
# installed in every image.
RUN curl -fsSL https://opencode.ai/install | bash \
    && cp /root/.opencode/bin/opencode /usr/local/bin/opencode

# Codex is selected at runtime, just like Claude Code and opencode.
ARG CODEX_CACHE_BUST=0
RUN npm install -g @openai/codex

COPY prepare-auth.py /usr/local/lib/claude-sandbox/prepare-auth.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV UV_PROJECT_ENVIRONMENT=.venv-container \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    UV_PYTHON_INSTALL_DIR=/home/dev/.local/share/uv/python

WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["claude", "--dangerously-skip-permissions"]
