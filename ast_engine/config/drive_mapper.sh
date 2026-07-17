#!/bin/bash
#
# creates and mounts windows shares via drvfs
# Intended to work in WSL. Containerized deployments may need a different method

while IFS='|' read -r share target; do
   [[ -z "$share" ]] && continue
   echo "$target"
   sudo mkdir -p "$target"
   sudo mount -t drvfs "$share" "$target" 
done < drive_map.conf
