FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu24.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-venv \
    git curl wget sudo gosu acl \
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

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /workspace

ENTRYPOINT ["/entrypoint.sh"]
CMD ["claude", "--dangerously-skip-permissions"]
