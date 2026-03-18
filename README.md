# claude-sandbox

A Docker-based sandbox for running Claude Code with `--dangerously-skip-permissions` safely. Designed for deep learning workflows with NVIDIA GPU passthrough.

## What it does

- Runs Claude Code inside a Docker container so it can't affect your host system
- Passes through NVIDIA GPUs for deep learning workloads
- Bind-mounts your project directory so you can edit files from both host (VS Code) and container (Claude Code)
- Forwards your Claude subscription credentials (no re-login needed)
- Enables voice mode (`/voice`) via PulseAudio/PipeWire passthrough
- Auto-rebuilds the container image on each run
- Auto-detects rootless vs rootful Docker and applies appropriate security settings

## Prerequisites

- Linux with Docker installed (rootless or rootful)
- NVIDIA GPU with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Claude Code installed on the host and logged in (for subscription auth), or an `ANTHROPIC_API_KEY`
- PulseAudio or PipeWire (for voice mode)

## Setup

```bash
git clone <this-repo> ~/claude-sandbox
chmod +x ~/claude-sandbox/claude-sandbox
```

Optionally add to your PATH:

```bash
ln -s ~/claude-sandbox/claude-sandbox ~/.local/bin/claude-sandbox
```

The first run will build the Docker image (downloads ~10GB CUDA base image).

## Usage

```bash
# Run in current directory
~/claude-sandbox/claude-sandbox

# Run in a specific project
~/claude-sandbox/claude-sandbox ~/projects/my-dl-project

# Enable host networking (rootful Docker only — always on for rootless)
~/claude-sandbox/claude-sandbox --host-network ~/projects/my-dl-project
```

The wrapper auto-detects whether Docker is rootless or rootful and prints the detected mode at startup. Use `--host-network` when you need the container to access services on localhost (e.g., a dev server on port 8080).

Claude Code starts with `--dangerously-skip-permissions` inside the container. Your project files are mounted at `/workspace/project`.

### Authentication

The wrapper supports two auth methods:

1. **Claude subscription (default)**: If you've logged into Claude Code on the host (`claude` then follow OAuth flow), credentials are automatically forwarded to the container.
2. **API key**: Export `ANTHROPIC_API_KEY` before running.

### Voice mode

Voice mode (`/voice`) works out of the box. The container routes audio through your host's PulseAudio/PipeWire.

### Editing files

Files are bind-mounted, so you can:
- Edit in VS Code on the host while Claude Code works inside the container
- Run `git push` from the host (no git credentials are passed to the container)
- Changes from either side are immediately visible to the other

### Options

```
Usage: claude-sandbox [--host-network] [project-dir]

Options:
  --host-network  Use host networking (always enabled for rootless Docker,
                  opt-in for rootful Docker)

Environment variables:
  CLAUDE_SANDBOX_MODE=rootless|rootful  Override Docker mode auto-detection
  ANTHROPIC_API_KEY=sk-ant-...          Use API key instead of subscription
```

## Security model

### Rootless Docker (recommended)

In rootless mode, the Docker daemon runs without root privileges. Container UID 0 maps to your host user, making privilege escalation impossible at the kernel level.

The sandbox uses `network_mode: host` for convenience since the container's network namespace is already user-namespaced.

Security properties:
- Container root = your host user (no privilege escalation possible)
- Claude Code runs as non-root `dev` user inside the container
- Only your project directory is exposed, not your home directory or system files
- No git/SSH credentials are passed to the container
- ACLs ensure both the host user and container user can read/write project files

### Rootful Docker

In rootful mode, the Docker daemon runs as root. The sandbox applies additional hardening:

- **No host networking** (default): Uses Docker's default bridge network instead of `network_mode: host`. The container can reach the internet (for Anthropic API calls) but cannot bind host ports or access host-only localhost services. Use `--host-network` to opt in to host networking when needed.
- **`no-new-privileges`**: Prevents any process in the container from gaining additional privileges via setuid/setgid binaries.
- **Minimal capabilities**: Drops all Linux capabilities except the minimum needed for container startup (`CHOWN`, `SETUID`, `SETGID`, `FOWNER`, `DAC_OVERRIDE`). These are used only by the entrypoint script; Claude Code runs as non-root and has no capabilities.

Security properties:
- Claude Code runs as non-root `dev` user inside the container
- Only your project directory is exposed, not your home directory or system files
- No git/SSH credentials are passed to the container
- No host network access
- No capability escalation possible

## What's inside the container

- CUDA 12.6 + cuDNN (Ubuntu 24.04)
- Python 3.12 + pip + venv
- Node.js 22
- Claude Code (native binary with voice support)
- uv (Python package manager)
- git, curl, wget, build-essential, cmake

## File structure

```
├── Dockerfile                  # Container image: CUDA + Python + Claude Code + uv
├── docker-compose.yml          # Base shared configuration (GPU, audio, volumes)
├── docker-compose.rootless.yml      # Rootless override: host networking
├── docker-compose.rootful.yml       # Rootful override: security hardening
├── docker-compose.host-network.yml  # Optional overlay: host networking for rootful
├── entrypoint.sh               # Permission setup, auth forwarding, ALSA→PulseAudio routing
├── claude-sandbox              # Convenience wrapper script (auto-detects Docker mode)
└── README.md
```

## Customization

### Adding Python packages to the base image

Add to the Dockerfile:

```dockerfile
RUN pip install torch torchvision --break-system-packages
```

### Using without NVIDIA GPU

Remove `runtime: nvidia` and the `NVIDIA_*` environment variables from `docker-compose.yml`.

### Disabling voice mode

Remove the PulseAudio-related volumes and environment variables from `docker-compose.yml`, and the `sox`/`alsa`/`pulseaudio` packages from the Dockerfile.
