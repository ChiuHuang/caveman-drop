#!/bin/sh
# CaveMan Drop — server bootstrap / auto-update script.
# POSIX sh compatible (pelican/pterodactyl runs it as `sh ./deploy.sh`,
# where bash-only `[[ ]]` is a syntax error).
set -e

GIT_ADDRESS="https://github.com/ChiuHuang/caveman-drop.git"
AUTO_UPDATE="1"
REQUIREMENTS_FILE="requirements.txt"
PY_PACKAGES=""
PY_FILE="-m gunicorn app:app -w 1 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:20042"

if [ ! -d .git ]; then git init && git remote add origin "$GIT_ADDRESS" && git fetch && git branch -M main && git reset --hard origin/main && git branch --set-upstream-to=origin/main main; elif [ "$AUTO_UPDATE" = "1" ]; then echo "Pulling updates..."; git pull --ff-only origin main; fi
if [ ! -d .venv ]; then echo "Creating venv..."; python3 -m venv .venv; fi
if [ ! -f .env ] && [ -f .env.example ]; then echo "Creating .env from example (edit PASSWORD)..."; cp .env.example .env; fi
if [ -f "$REQUIREMENTS_FILE" ]; then REQ_HASH=$(sha256sum "$REQUIREMENTS_FILE" | awk '{print $1}'); OLD_HASH=$(cat .venv/.req_hash 2>/dev/null || echo ""); if [ "$REQ_HASH" != "$OLD_HASH" ]; then echo "Requirements changed, installing..."; .venv/bin/pip install --quiet -r "$REQUIREMENTS_FILE" && echo "$REQ_HASH" > .venv/.req_hash && echo "Requirements installed"; else echo "Requirements unchanged, skipping pip install"; fi; fi
if [ -n "$PY_PACKAGES" ]; then PKG_HASH=$(echo -n "$PY_PACKAGES" | sha256sum | awk '{print $1}'); OLD_PKG_HASH=$(cat .venv/.pkg_hash 2>/dev/null || echo ""); if [ "$PKG_HASH" != "$OLD_PKG_HASH" ]; then echo "Installing extra packages..."; .venv/bin/pip install --quiet $PY_PACKAGES && echo "$PKG_HASH" > .venv/.pkg_hash; else echo "Extra packages unchanged"; fi; fi
.venv/bin/python $PY_FILE
