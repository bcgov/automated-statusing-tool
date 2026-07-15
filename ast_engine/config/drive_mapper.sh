#!/bin/sh
#
# creates and mounts windows shares via drvfs
# Intended to work in WSL. Containerized deployments may need a different method

# set -uo pipefail


SHARE_TABLE=(
  "\\\\spatialfiles.bcgov\work|/mnt/w|WIN_W_DRIVE"
#   "D:|/mnt/d|WIN_D_DRIVE"
#   "E:|/mnt/e|WIN_E_DRIVE"
#   "\\\\fileserver\\projects|/mnt/projects|WIN_PROJECTS_SHARE"
#   "\\\\fileserver\\data|/mnt/data|WIN_DATA_SHARE"
)

ENV_FILE="win-shares.env" # Change to relative directory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
 
log()  { echo "[mount-win-shares] $*"; }
err()  { echo "[mount-win-shares] ERROR: $*" >&2; }


mount_one() {
  local win_share="$1" mount_point="$2" env_var="$3"
 
  if mountpoint -q "$mount_point" 2>/dev/null; then
    log "Already mounted: $mount_point"
  else
    log "Mounting '$win_share' -> '$mount_point'"
    sudo mkdir -p "$mount_point"
 
    if ! sudo mount -t drvfs "$win_share" "$mount_point" -o metadata; then
      err "Failed to mount '$win_share' at '$mount_point'"
      return 1
    fi
  fi
 
  # Export for the current shell (only takes effect if this script is sourced)
  export "$env_var"="$mount_point"
  log "  $env_var=$mount_point"
 
  # Persist to env file for later sourcing / other processes
  # Remove any prior definition of this var, then append the current one
  if [[ -f "$ENV_FILE" ]]; then
    sed -i "/^export ${env_var}=/d" "$ENV_FILE"
  fi
  echo "export ${env_var}=\"${mount_point}\"" >> "$ENV_FILE"
}

umount_one() {
  local win_share="$1" mount_point="$2" env_var="$3"
 
  if mountpoint -q "$mount_point" 2>/dev/null; then
    log "Unmounting $mount_point"
    sudo umount "$mount_point" || err "Failed to unmount $mount_point"
  else
    log "Not mounted: $mount_point"
  fi
 
  unset "$env_var" 2>/dev/null || true
}

list_table() {
  printf "%-28s %-18s %s\n" "WINDOWS SHARE" "MOUNT POINT" "ENV VAR"
  printf "%-28s %-18s %s\n" "-------------" "-----------" "-------"
  local row win_share mount_point env_var
  for row in "${SHARE_TABLE[@]}"; do
    IFS='|' read -r win_share mount_point env_var <<< "$row"
    printf "%-28s %-18s %s\n" "$win_share" "$mount_point" "$env_var"
  done
}

do_mount_all() {
  : > "$ENV_FILE"  # start fresh
  local row win_share mount_point env_var
  for row in "${SHARE_TABLE[@]}"; do
    IFS='|' read -r win_share mount_point env_var <<< "$row"
    mount_one "$win_share" "$mount_point" "$env_var"
  done
  log "Env vars written to $ENV_FILE"
  if ! is_sourced; then
    log "Tip: run 'source ${BASH_SOURCE[0]}' to load these vars into your current shell."
  fi
}
 
do_umount_all() {
  local row win_share mount_point env_var
  for row in "${SHARE_TABLE[@]}"; do
    IFS='|' read -r win_share mount_point env_var <<< "$row"
    umount_one "$win_share" "$mount_point" "$env_var"
  done
}

main() {
  local cmd="${1:-mount}"
  case "$cmd" in
    mount)   do_mount_all ;;
    umount|unmount) do_umount_all ;;
    list)    list_table ;;
    *)
      err "Unknown command: $cmd"
      echo "Usage: $0 [mount|umount|list]"
      return 1
      ;;
  esac
}
 
main "$@"
