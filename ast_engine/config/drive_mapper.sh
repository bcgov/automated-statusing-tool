#!/bin/bash
#
# creates and mounts windows shares via drvfs
# Intended to work in WSL. Containerized deployments may need a different method
# Run this to mount the drives required for data access.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
CONFIG_DIR="$SCRIPT_DIR/drive_map.conf"

while IFS='|' read -r share target; do
   [[ -z "$share" ]] && continue
   echo "$target"
   sudo mkdir -p "$target"
   sudo mount -t drvfs "$share" "$target" 
done < $CONFIG_DIR
