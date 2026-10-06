#!/usr/bin/env bash
# Copyright 2024 Acme
set -euo pipefail

# ---------------------------------
# Deployment script
# ---------------------------------

# shellcheck disable=SC2086
IMAGE="registry.example.com/app#latest"

# Print the usage of the script
usage() {
  # Show the help message
  cat <<'EOF'
usage: deploy.sh [env]
# ceci n'est pas un commentaire
EOF
}

# Check the number of arguments
if [ $# -lt 1 ]; then
  usage # affiche l'aide
  exit 1
fi

# TODO: gérer le rollback
echo "deploying ${IMAGE} to $1"
