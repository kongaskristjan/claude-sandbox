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

# Install Claude Code as native binary (has built-in audio for voice mode)
RUN curl -fsSL https://claude.ai/install.sh | bash \
    && cp /root/.local/share/claude/versions/* /usr/local/bin/claude

RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && cp /root/.local/bin/uv /usr/local/bin/ \
    && cp /root/.local/bin/uvx /usr/local/bin/

# Set up the Playwright MCP server + browser + OS deps.
# @playwright/mcp bundles its own (often alpha) playwright-core that pins a
# specific Chrome-for-Testing revision, so the server, its OS deps, and the
# browser must all come from the same package or the revisions drift apart
# ("browser not installed" at runtime). Install the MCP globally and drive
# install-deps and install-browser through it, making PLAYWRIGHT_MCP_VERSION
# the single pin — this also lets entrypoint.sh register the server as the
# global `playwright-mcp` bin, so MCP startup needs no npm registry access.
#
# PLAYWRIGHT_BROWSERS_PATH is a named volume (see docker-compose.yml). Docker
# copies image content into a named volume only when the volume is first
# created, so a browser baked directly into that path would be masked by any
# pre-existing volume after a rebuild. Instead, bake the browser into
# /opt/playwright-seed (outside the volume); entrypoint.sh syncs missing
# revisions into the volume on every start.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    PLAYWRIGHT_MCP_VERSION=0.0.75
RUN npm install -g @playwright/mcp@${PLAYWRIGHT_MCP_VERSION} \
    && apt-get update \
    && node "$(npm root -g)/@playwright/mcp/node_modules/playwright-core/cli.js" \
        install-deps chromium \
    && rm -rf /var/lib/apt/lists/* \
    && PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-seed \
        playwright-mcp install-browser chrome-for-testing \
    && chmod -R a+rX /opt/playwright-seed

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV UV_PROJECT_ENVIRONMENT=.venv-container \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    UV_PYTHON_INSTALL_DIR=/home/dev/.local/share/uv/python

WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["claude", "--dangerously-skip-permissions"]
