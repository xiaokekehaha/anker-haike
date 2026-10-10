#!/bin/sh
set -eu

task_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "$task_directory/.env"

exec ssh -N -T \
  -i "${SSH_IDENTITY_FILE:?SSH_IDENTITY_FILE is required}" \
  -o IdentitiesOnly=yes \
  -o BatchMode=yes \
  -o StrictHostKeyChecking=yes \
  -o "HostKeyAlias=${SSH_HOST_KEY_ALIAS:-$PUBLIC_IP}" \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -R 127.0.0.1:15173:127.0.0.1:5173 \
  "ubuntu@${PUBLIC_IP:?PUBLIC_IP is required}"
