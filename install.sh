#!/usr/bin/env bash
set -Eeuo pipefail

IMAGE="${FREELLM_IMAGE:-ghcr.io/newaran/freellm:latest}"
PORT="${FREELLM_PORT:-8080}"
NAME="${FREELLM_CONTAINER_NAME:-freellm}"
VOLUME="${FREELLM_VOLUME:-freellm-data}"

say(){ printf '\033[1;34m[FreeLLM]\033[0m %s\n' "$*"; }
fail(){ printf '\033[1;31m[FreeLLM]\033[0m %s\n' "$*" >&2; exit 1; }

install_docker_debian(){
  local sudo_cmd=""
  if [ "$(id -u)" -ne 0 ]; then command -v sudo >/dev/null || fail "Docker is missing and sudo is not available."; sudo_cmd="sudo"; fi
  say "Docker was not found. Installing Docker from the Debian/Ubuntu package repository…"
  $sudo_cmd apt-get update
  $sudo_cmd apt-get install -y docker.io
  $sudo_cmd systemctl enable --now docker || true
  if [ "$(id -u)" -ne 0 ]; then say "Docker installed. This run will use sudo; log out/in later if you add your user to the docker group."; fi
}

if ! command -v docker >/dev/null 2>&1; then
  if command -v apt-get >/dev/null 2>&1; then install_docker_debian; else fail "Docker is not installed. Install Docker Engine, then run this script again."; fi
fi
DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  if command -v sudo >/dev/null && sudo docker info >/dev/null 2>&1; then DOCKER="sudo docker"; else fail "Docker daemon is not available. Start Docker and run again."; fi
fi
say "Pulling $IMAGE"
if ! $DOCKER pull "$IMAGE"; then fail "Could not pull the image. If the GitHub Container Registry package is private, run: docker login ghcr.io -u YOUR_GITHUB_USERNAME, then retry."; fi
if $DOCKER ps -a --format '{{.Names}}' | grep -qx "$NAME"; then say "Replacing existing container $NAME"; $DOCKER rm -f "$NAME" >/dev/null; fi
$DOCKER volume create "$VOLUME" >/dev/null
$DOCKER run -d --name "$NAME" --restart unless-stopped -p "$PORT:8080" -v "$VOLUME:/data" "$IMAGE" >/dev/null
say "Container started. Waiting for health check…"
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${PORT}/health" >/dev/null 2>&1; then say "Ready: http://127.0.0.1:${PORT}"; say "On a VPS, open: http://SERVER_IP:${PORT}"; exit 0; fi
  sleep 2
done
$DOCKER logs --tail 80 "$NAME" || true
fail "Container did not become healthy. Check the logs above."
