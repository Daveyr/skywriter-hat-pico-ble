# Skywriter development sandbox for agentic (Ralph-loop) development.
#
# Build:  docker build -t skywriter-dev .
#         (if your uid/gid are not 1000, add --build-arg USER_UID=$(id -u) USER_GID=$(id -g))
#
# Why it is built this way:
# - Alpine keeps the image small. Python 3.12 matches the project's Python target.
# - The repository is NOT copied into the image. It is bind-mounted at /workspace so
#   the agent's edits and commits land on the host, and nothing project-specific or
#   secret is baked into image layers.
# - The process runs as an unprivileged user whose uid/gid match the host user (1000
#   by default), with no sudo. The agent cannot modify the image's system files.
# - The Pico toolchain (arduino-cli + rp2040 core, several hundred MB) is installed on
#   first use into a volume instead of the image, so the image stays small.
#   ARDUINO_DIRECTORIES_USER points arduino-cli's *user* directory (whose
#   `libraries/` subfolder receives `lib install`) inside the volume, so
#   installed libraries survive --rm reruns instead of vanishing with the
#   container's $HOME. (arduino-cli appends `/libraries` itself — do not
#   point it at the libraries folder directly.)
#
# Hardened run (dangerously-skip-permissions: the container is the safety boundary):
#   docker run -it --rm \
#     --cap-drop ALL --security-opt no-new-privileges:true \
#     --pids-limit 512 --memory 8g \
#     -v "$PWD:/workspace" \
#     -v skywriter-opencode:/home/dev/.local/share/opencode \
#     -v skywriter-arduino:/home/dev/.arduino15 \
#     -v "$HOME/.gitconfig:/home/dev/.gitconfig:ro" \
#     -v "$HOME/.ssh/known_hosts:/home/dev/.ssh/known_hosts:ro" \
#     -v "$HOME/.ssh/skywriter_deploy_key:/home/dev/.ssh/id_ed25519:ro" \
#     skywriter-dev opencode --auto
#
# Every host file mounted above must already exist, or Docker creates an empty
# directory in its place. Use a repo-scoped deploy key (write access to this repository
# only), not your personal key or a forwarded ssh-agent, so a runaway agent cannot push
# to other repositories.
#
# Ralph loop (non-interactive; --auto approves anything not explicitly denied):
#   ... skywriter-dev bash -c 'while :; do opencode run --auto "$(cat PROMPT.md)"; done'
#
# First Pico compile in a fresh volume: arduino-cli core install rp2040:rp2040@6.3.1
#
# Not available in the container: flashing the Pico (needs host USB and udisks) and
# the firmware updater (needs real I2C hardware). Run those on the host. Debian
# packaging (packaging/makeall.sh) needs debhelper and lintian, which Alpine lacks.

FROM alpine:3.22

ARG USER_UID=1000
ARG USER_GID=1000
ARG ARDUINO_CLI_VERSION=1.5.1
ARG OPENCODE_VERSION=2.2.5

ENV LANG=C.UTF-8 \
    GIT_PAGER=cat \
    GIT_TERMINAL_PROMPT=0 \
    PYTHONDONTWRITEBYTECODE=1 \
    ARDUINO_BOARD_MANAGER_ADDITIONAL_URLS=https://github.com/earlephilhower/arduino-pico/releases/download/global/package_rp2040_index.json \
    ARDUINO_DIRECTORIES_USER=/home/dev/.arduino15

# The arduino-pico core ships glibc-linked binaries (arm-none-eabi-gcc, picotool). gcompat
# and libstdc++ let them run on musl; eudev-libs supplies the libudev.so.1 that picotool
# needs to build the UF2 image.
RUN apk add --no-cache \
        bash ca-certificates curl git jq openssh-client ripgrep tini \
        gcompat libstdc++ eudev-libs \
        python3 py3-mock py3-pip py3-pytest py3-setuptools

RUN case "$(uname -m)" in \
        x86_64)  OC_ARCH=x64;   ARDUINO_ARCH=64bit ;; \
        aarch64) OC_ARCH=arm64; ARDUINO_ARCH=ARM64 ;; \
        *) echo "unsupported architecture: $(uname -m)" >&2; exit 1 ;; \
    esac && \
    curl -fsSL "https://github.com/arduino/arduino-cli/releases/download/v${ARDUINO_CLI_VERSION}/arduino-cli_${ARDUINO_CLI_VERSION}_Linux_${ARDUINO_ARCH}.tar.gz" \
        | tar -xz -C /usr/local/bin arduino-cli && \
    curl -fsSL "https://registry.npmjs.org/@opencode/cli-linux-${OC_ARCH}-musl/-/cli-linux-${OC_ARCH}-musl-${OPENCODE_VERSION}.tgz" \
        | tar -xz -C /tmp && \
    install -m 0755 /tmp/package/bin/opencode /usr/local/bin/opencode && \
    rm -rf /tmp/package

RUN addgroup -g "$USER_GID" dev && \
    adduser -D -u "$USER_UID" -G dev -h /home/dev -s /bin/bash dev && \
    git config --system --add safe.directory /workspace && \
    install -d -o dev -g dev /workspace

USER dev
WORKDIR /workspace

RUN install -d -m 0700 /home/dev/.ssh && \
    install -d /home/dev/.config/opencode /home/dev/.local/share/opencode \
               /home/dev/.arduino15 /home/dev/.arduino15/libraries && \
    echo '{"$schema":"https://opencode.ai/config.json","model":"opencode-go/glm-5.3-flash","permissions":[{"action":"*","resource":"*","effect":"allow"}]}' \
        > /home/dev/.config/opencode/opencode.json && \
    ln -s /workspace/arduino/Skywriter /home/dev/.arduino15/libraries/Skywriter

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["bash"]
