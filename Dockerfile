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

# Set up the browser + OS deps for the Playwright MCP server.
# @playwright/mcp bundles its own (often alpha) playwright-core that pins a
# specific Chrome-for-Testing revision, so installing the *stable* playwright
# browser leaves a revision mismatch ("browser not installed") at runtime. We
# therefore install the browser via the MCP's own installer, which guarantees a
# match with the bundled playwright-core. PLAYWRIGHT_BROWSERS_PATH is a named
# volume (see docker-compose.yml), so this baked browser is only a zero-setup
# seed: if a newer @playwright/mcp needs a newer revision, run-time
#   npx -y @playwright/mcp@<ver> install-browser chrome-for-testing
# persists into the volume and is reused on later runs — no Dockerfile pin to
# bump. OS deps need root, so they are baked here at build time.
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright-browsers \
    PLAYWRIGHT_MCP_VERSION=0.0.75
RUN npx -y playwright@latest install-deps chromium \
    && npx -y @playwright/mcp@${PLAYWRIGHT_MCP_VERSION} install-browser chrome-for-testing \
    && chmod -R a+rX /opt/playwright-browsers \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV UV_PROJECT_ENVIRONMENT=.venv-container \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/home/dev/.cache/uv \
    UV_PYTHON_INSTALL_DIR=/home/dev/.local/share/uv/python

WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["claude", "--dangerously-skip-permissions"]
