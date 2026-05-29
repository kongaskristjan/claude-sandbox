#!/bin/bash
set -e

# In rootless Docker, host UID 1000 maps to container UID 0 (root).
# Claude Code refuses to run as root, so we drop to user "dev".
# We use ACLs to ensure both root (=host user) and dev can read/write
# all project files.

if [ -d /workspace/project ]; then
    # Give dev access to existing host-owned files
    setfacl -R -m u:dev:rwX /workspace/project 2>/dev/null || true
    # Default ACL: new files/dirs automatically grant access to both
    setfacl -R -d -m u:dev:rwX /workspace/project 2>/dev/null || true
    setfacl -R -d -m u:0:rwX /workspace/project 2>/dev/null || true
fi

# Ensure dev owns the .claude config directory (Docker volume starts as root)
chown -R dev:dev /home/dev/.claude 2>/dev/null || true

# Same for the uv cache volume
mkdir -p /home/dev/.cache/uv
chown -R dev:dev /home/dev/.cache 2>/dev/null || true

# Same for the uv-managed Python interpreter volume
mkdir -p /home/dev/.local/share/uv/python
chown -R dev:dev /home/dev/.local 2>/dev/null || true

# Same for the Playwright browsers volume, so the MCP can install newer browser
# revisions at runtime and have them persist across sessions
mkdir -p /opt/playwright-browsers
chown -R dev:dev /opt/playwright-browsers 2>/dev/null || true

# Copy host auth files so dev user can use the existing subscription
mkdir -p /home/dev/.claude
if [ -f /tmp/host-credentials.json ]; then
    cp /tmp/host-credentials.json /home/dev/.claude/.credentials.json
    chown dev:dev /home/dev/.claude/.credentials.json
    chmod 600 /home/dev/.claude/.credentials.json
fi
if [ -f /tmp/host-claude.json ]; then
    cp /tmp/host-claude.json /home/dev/.claude.json
    chown dev:dev /home/dev/.claude.json
    chmod 600 /home/dev/.claude.json
fi

# Register the Playwright MCP server, pinned to the browser revision baked into
# the image, with the flags this sandbox needs (--browser chromium, since no
# system Chrome exists; --headless, since there is no display). This way the
# agent gets a working browser without knowing any sandbox internals. Done here,
# after the host config copy, because that copy would clobber a build-time
# registration. remove-then-add keeps it idempotent across restarts. Set
# CLAUDE_SANDBOX_NO_PLAYWRIGHT=1 to skip.
if [ -z "$CLAUDE_SANDBOX_NO_PLAYWRIGHT" ] && [ -n "$PLAYWRIGHT_MCP_VERSION" ]; then
    gosu dev env HOME=/home/dev claude mcp remove playwright -s user 2>/dev/null || true
    gosu dev env HOME=/home/dev claude mcp add playwright -s user -- \
        npx -y "@playwright/mcp@${PLAYWRIGHT_MCP_VERSION}" --headless --browser chromium \
        >/dev/null 2>&1 || true
fi

# Allow dev to access PulseAudio socket
PULSE_DIR=$(find /run/user -maxdepth 2 -name pulse -type d 2>/dev/null | head -1)
if [ -n "$PULSE_DIR" ]; then
    setfacl -R -m u:dev:rwX "$PULSE_DIR" 2>/dev/null || true
fi

# Route ALSA through PulseAudio so Claude Code's native audio module works
# (it uses ALSA directly, but no sound cards are passed to the container)
cat > /etc/asound.conf << 'ASOUNDEOF'
pcm.!default {
    type pulse
}
ctl.!default {
    type pulse
}
ASOUNDEOF

# Mark the mounted project directory as safe for git (owned by root, run as dev)
gosu dev git config --global --add safe.directory /workspace/project

# Copy host git identity (name, email, default branch) but not credentials
if [ -f /tmp/host-gitconfig ]; then
    git_name=$(git config -f /tmp/host-gitconfig user.name 2>/dev/null || true)
    git_email=$(git config -f /tmp/host-gitconfig user.email 2>/dev/null || true)
    default_branch=$(git config -f /tmp/host-gitconfig init.defaultBranch 2>/dev/null || true)
    if [ -n "$git_name" ]; then
        gosu dev git config --global user.name "$git_name"
    fi
    if [ -n "$git_email" ]; then
        gosu dev git config --global user.email "$git_email"
    fi
    if [ -n "$default_branch" ]; then
        gosu dev git config --global init.defaultBranch "$default_branch"
    fi
fi

exec gosu dev "$@"
