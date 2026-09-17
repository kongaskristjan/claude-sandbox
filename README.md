# claude-sandbox

A Docker-based sandbox for running Claude Code with `--dangerously-skip-permissions` safely. Supports CPU-only, NVIDIA GPU, and Rust workflows.

## What it does

- Runs Claude Code inside a Docker container so it can't affect your host system
- Ships a lightweight CPU image by default; opt in to a CUDA image with `--gpu` for deep learning workloads, or a Rust image with `--rust`
- Bind-mounts your project directory so you can edit files from both host (VS Code) and container (Claude Code)
- Forwards your Claude subscription credentials (no re-login needed)
- Shares your personal skills (`~/.claude/skills`), so they work inside and outside the sandbox
- Enables voice mode (`/voice`) via PulseAudio/PipeWire passthrough
- Auto-rebuilds the container image on each run
- Auto-detects rootless vs rootful Docker and applies appropriate security settings

## Prerequisites

- Linux with Docker installed (rootless or rootful), or macOS with Docker Desktop
- NVIDIA GPU with [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) (only required when using `--gpu`)
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

The first run will build the Docker image. The default CPU image is small; `--gpu` switches to a CUDA base image (~10GB download on first build); `--rust` builds a separate image with a rustup toolchain instead of Python.

## Usage

```bash
# Run in current directory (CPU-only)
~/claude-sandbox/claude-sandbox

# Run in a specific project
~/claude-sandbox/claude-sandbox ~/projects/my-dl-project

# Run opencode instead of Claude Code (same image, chosen at runtime)
~/claude-sandbox/claude-sandbox --opencode ~/projects/my-project

# Point opencode at an OpenAI-compatible server on the host (e.g. a local
# 'openai serve' on port 8080) instead of a hosted provider
~/claude-sandbox/claude-sandbox --opencode --port 8080 ~/projects/my-project

# Enable NVIDIA GPU passthrough with the CUDA image
~/claude-sandbox/claude-sandbox --gpu ~/projects/my-dl-project

# Use the Rust image (rustup toolchain, cargo caches, no Python/CUDA)
~/claude-sandbox/claude-sandbox --rust ~/projects/my-rust-project

# Enable host networking (rootful Docker only — always on for rootless)
~/claude-sandbox/claude-sandbox --host-network ~/projects/my-dl-project
```

The wrapper auto-detects whether Docker is rootless or rootful and prints the detected mode at startup. Use `--host-network` when you need the container to access services on localhost (e.g., a dev server on port 8080).

Claude Code starts with `--dangerously-skip-permissions` inside the container (opencode starts with the equivalent `--auto`). Your project files are mounted at `/workspace/project`.

### Authentication

The wrapper supports two auth methods:

1. **Claude subscription (default)**: If you've logged into Claude Code on the host (`claude` then follow OAuth flow), credentials are automatically forwarded to the container.
2. **API key**: Export `ANTHROPIC_API_KEY` before running.

On macOS, Claude Code stores subscription credentials in the login Keychain
rather than `~/.claude/.credentials.json`, so there is no file to forward. The
wrapper exports the Keychain item (`Claude Code-credentials`) to a private
`0600` temp file for the life of the run, mounts that, and deletes it on exit.
Expect a Keychain prompt on first use.

**opencode** (`--opencode`) authenticates differently from Claude Code:

- **API key**: Export `ANTHROPIC_API_KEY` before running — opencode honors it
  for the Anthropic provider.
- **Forwarded login**: If you've logged into opencode on the host, the wrapper
  forwards `~/.local/share/opencode/auth.json` (read-only) into the container.

opencode's config lives at `~/.config/opencode/opencode.json` on the host and is
forwarded the same way; its state (the running `auth.json`, `opencode.db`)
persists across runs in the `opencode-data` named volume. Unlike Claude
subscription auth, a missing opencode auth file is **not** fatal — opencode can
also log in interactively inside the container.

**`--port <port>`** points opencode at an OpenAI-compatible server running on the
host (for example a local `openai serve`) instead of a hosted provider. The
wrapper auto-enables host networking so the container can reach the host, and the
entrypoint merges a `local` provider into opencode's config targeting
`http://127.0.0.1:<port>/v1`, auto-discovering the server's models from
`/v1/models` and pre-selecting the first one so `--auto` starts without a prompt
(a user-set `model` in the forwarded config is left alone). It's opencode-only:
passing `--port` without `--opencode` is an error. Override the target host with
`OPENCODE_API_HOST` (default `127.0.0.1`, correct under host networking).

### Voice mode

Voice mode (`/voice`) works out of the box. The container routes audio through your host's PulseAudio/PipeWire.

### GPU sharing (CUDA MPS)

With `--gpu`, the entrypoint starts the CUDA MPS control daemon
(`nvidia-cuda-mps-control -d`) so that several processes hitting the same GPU
run their kernels concurrently in one context instead of being time-sliced —
useful when Claude Code runs training, evaluation, and a notebook side by side.
The pipe and log directories are `/tmp/nvidia-mps` and `/var/log/nvidia-mps`
(exported as `CUDA_MPS_PIPE_DIRECTORY` / `CUDA_MPS_LOG_DIRECTORY`).

Set `CLAUDE_SANDBOX_NO_MPS=1` to skip it — MPS clients share one server process,
so a fatal fault in one can take down the others, and Nsight profiling of an MPS
client is restricted. The CPU image ignores the variable; the daemon only starts
when a GPU is actually passed through.

### Rust image

`--rust` builds `Dockerfile.rust`: Ubuntu 24.04 with a rustup-managed stable
toolchain (plus `rustfmt` and `clippy`), Node.js, Claude Code and the Playwright
MCP — but no Python tooling and no CUDA. Common `-sys` crate build inputs
(`pkg-config`, `libssl-dev`, `cmake`, `build-essential`) are present.

Cargo's caches are persistent named volumes, the same way the uv cache is, so
dependencies are downloaded and compiled once instead of once per container:

| Volume | Path | Contents |
| --- | --- | --- |
| `cargo-registry` | `$CARGO_HOME/registry` | downloaded and unpacked crates |
| `cargo-git` | `$CARGO_HOME/git` | git dependency checkouts |
| `cargo-target` | `$CARGO_HOME/target` | build artifacts (`CARGO_TARGET_DIR`) |

Two consequences of `CARGO_TARGET_DIR=/home/dev/.cargo/target`:

- Builds inside the sandbox do **not** write a `target/` into your project
  directory, so they can't collide with a `target/` the host built with a
  different toolchain (the same reasoning behind `UV_PROJECT_ENVIRONMENT=.venv-container`
  in the Python images). Artifacts live at `/home/dev/.cargo/target/<profile>/`
  inside the container; `cargo run` and `cargo test` find them as usual. Run
  `CARGO_TARGET_DIR=target cargo build` for the rare case where you want the
  output in the project directory instead.
- All projects share one target directory, so cargo reuses dependency builds
  whose fingerprint (version, features, profile, compiler) matches across
  projects. `docker volume rm claude-sandbox_cargo-target` clears it if it grows
  too large.

The toolchain itself lives in `$RUSTUP_HOME` (`/home/dev/.rustup`) and
`$CARGO_HOME/bin` — image content, not volumes, so a rebuild always wins over
what an old volume holds. `rustup update` and `cargo install` work inside a
session but, like anything outside the cache volumes, don't survive it.

### Playwright MCP (browser automation)

A headless Chromium build and its OS dependencies are pre-baked, and the
[Playwright MCP server](https://github.com/microsoft/playwright-mcp) is
**auto-registered on container start** — so browser automation works with no
setup. The entrypoint registers it (user scope) pinned to the browser revision
baked into the image, with the flags this sandbox needs:

```bash
playwright-mcp --headless --browser chromium --isolated
```

- `--browser chromium` (not the default Chrome channel) — no system Google Chrome
  is installed, so the default channel fails; this targets the bundled Chromium.
- `--headless` — there is no display in the container.
- `--isolated` — keep the Chrome profile in memory. Without it, the MCP persists
  a profile per client cwd (so one per worktree) into the browsers volume, which
  grows without bound; the entrypoint prunes profiles older than a week.

Set `CLAUDE_SANDBOX_NO_PLAYWRIGHT=1` to skip registration (e.g. if you don't want
the server spawned for sessions that never touch a browser).

Notes:
- `@playwright/mcp` bundles its own playwright-core pinned to a specific browser
  revision. The image installs `@playwright/mcp@$PLAYWRIGHT_MCP_VERSION` globally
  and drives the browser install through it, avoiding the "browser not installed"
  revision mismatch you get from a stable `playwright install`. That one version
  pin covers the server, its OS deps, and the browser.
- `/opt/playwright-browsers` is a **persistent named volume**, so it masks
  whatever the image has at that path. The browser is therefore baked into
  `/opt/playwright-seed` inside the image, and the entrypoint copies any missing
  revision into the volume at start. To upgrade, bump `PLAYWRIGHT_MCP_VERSION`
  in the Dockerfile and rebuild — the next container start syncs the new
  revision in, even on machines whose volume already exists.

### Personal skills

Your host skills directory (`~/.claude/skills`) is bind-mounted read-only at
`/home/dev/.claude/skills`, so a skill you install once on the host is available
both when you run `claude` normally and when you run it in the sandbox. Drop a
`~/.claude/skills/<name>/SKILL.md` on the host and the next container start picks
it up — nothing to rebuild.

The container's `~/.claude` is a persistent named volume, which would otherwise
mask the host's skills; the mount targets a path *inside* that volume, and Docker
orders mounts by path depth, so the deeper bind wins. It's read-only: skills are
inputs, and the container has no business writing to the host's config.

### Editing files

Files are bind-mounted, so you can:
- Edit in VS Code on the host while Claude Code works inside the container
- Run `git push` from the host (no git credentials are passed to the container)
- Changes from either side are immediately visible to the other

### Options

```
Usage: claude-sandbox [--gpu|--rust] [--host-network] [--update] [--agents|--opencode] [--port <port>] [project-dir]

Options:
  --gpu           Use the CUDA image with NVIDIA GPU passthrough
                  (default: CPU-only ubuntu:24.04 image)
  --rust          Use the Rust image (rustup toolchain, no Python or
                  CUDA) with persistent cargo registry and build caches
  --host-network  Use host networking (always enabled for rootless Docker,
                  opt-in for rootful Docker)
  --update        Refresh the Claude Code binary in the image (other layers
                  stay cached); future runs reuse the refreshed layer
  --agents        Launch the background-agents view ('claude agents')
                  instead of an interactive session
  --opencode      Run opencode instead of Claude Code (same image; the agent
                  is selected at runtime, not baked into one)
  --port <port>   (--opencode only) Point opencode at an OpenAI-compatible
                  server running on the host at this port; auto-enables host
                  networking and auto-discovers the server's models

Environment variables:
  CLAUDE_SANDBOX_MODE=rootless|rootful  Override Docker mode auto-detection
  CLAUDE_SANDBOX_NO_MPS=1               Don't start the CUDA MPS control daemon
  ANTHROPIC_API_KEY=sk-ant-...          Use API key instead of subscription
```

`--update` writes a timestamp to `~/.cache/claude-sandbox/claude-update-stamp`
(or under `$XDG_CACHE_HOME`) and passes it to the build as `CLAUDE_CACHE_BUST`,
the build arg right before the Claude install layer. Only that layer and the
entrypoint copy are rebuilt; apt, node, uv and the Playwright browser stay
cached. Because the stamp persists and is passed on every run, later runs keep
using the refreshed layer instead of matching the stale one.

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

Every image:

- Node.js 22
- Claude Code (native binary with voice support)
- opencode (native binary; run it instead of Claude Code with `--opencode`)
- git, git-lfs, curl, wget, build-essential, cmake
- Headless Chromium + OS deps for the [Playwright MCP server](https://github.com/microsoft/playwright-mcp)

Per image:

| | default | `--gpu` | `--rust` |
| --- | --- | --- | --- |
| Base | Ubuntu 24.04 | CUDA 13.0 + cuDNN on Ubuntu 24.04 | Ubuntu 24.04 |
| Python 3.12 + pip + venv + uv | ✅ | ✅ | —* |
| CUDA toolkit / NVIDIA passthrough | — | ✅ | — |
| rustup (stable, rustfmt, clippy) + cargo caches | — | — | ✅ |

\* The Rust image installs no Python tooling, but a bare `python3` interpreter
comes in as a dependency of the NodeSource `nodejs` package.

## File structure

```
├── Dockerfile                  # Default CPU image: Ubuntu 24.04 + Python + Claude Code + uv
├── Dockerfile.cuda             # Optional CUDA image (used with --gpu)
├── Dockerfile.rust             # Optional Rust image (used with --rust)
├── docker-compose.yml          # Base shared configuration (audio, volumes)
├── docker-compose.rootless.yml      # Rootless override: host networking
├── docker-compose.rootful.yml       # Rootful override: security hardening
├── docker-compose.gpu.yml           # Optional overlay: CUDA image + NVIDIA runtime
├── docker-compose.rust.yml          # Optional overlay: Rust image + cargo cache volumes
├── docker-compose.host-network.yml  # Optional overlay: host networking for rootful
├── entrypoint.sh               # Permission setup, auth forwarding, ALSA→PulseAudio routing, CUDA MPS
├── claude-sandbox              # Convenience wrapper script (auto-detects Docker mode)
└── README.md
```

## Customization

### Adding Python packages to the base image

Add to the Dockerfile:

```dockerfile
RUN pip install torch torchvision --break-system-packages
```

### Disabling voice mode

Remove the PulseAudio-related volumes and environment variables from `docker-compose.yml`, and the `sox`/`alsa`/`pulseaudio` packages from the Dockerfile.
