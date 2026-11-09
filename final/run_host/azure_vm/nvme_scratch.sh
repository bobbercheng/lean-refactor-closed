#!/usr/bin/env bash
# Local NVMe scratch for the Azure CPU VM (lra-cpu1, Standard_D64ads_v7: 4 x 880 GiB "Microsoft NVMe Direct Disk v2", raw, unformatted).
# RAID0 over every direct-attached NVMe disk, ext4 labelled lra-scratch, mounted at /scratch (noatime), owned by lra.
# The disks are WIPED on every deallocate, so after each start this must run again (sudo; or enable lra-nvme-scratch.service, see
# infra/azure/README.md); after a plain reboot it re-assembles and mounts the existing array.
# Scratch only: compile temp dirs, caches, throwaway build trees. The repo, envs, ~/.elan and Docker stay on the OS disk.
# NOTE 2026-10-26: not run by the provisioning script (it formats disks); run it once by hand:
#   ssh ... 'sudo /usr/local/sbin/lra-nvme-scratch.sh'
set -eu
MNT=/scratch; LABEL=lra-scratch; OWNER=${LRA_SCRATCH_OWNER:-lra}
mountpoint -q "$MNT" && { echo "scratch: $MNT already mounted"; exit 0; }
mapfile -t DISKS < <(lsblk -dn -o NAME,MODEL | awk '/NVMe Direct Disk/ {print "/dev/" $1}' | sort)
[ "${#DISKS[@]}" -gt 0 ] || { echo "scratch: no local NVMe disks found"; exit 1; }
mkdir -p "$MNT"
DEV=$(blkid -L "$LABEL" 2>/dev/null || true)
if [ -z "$DEV" ]; then mdadm --assemble --scan > /dev/null 2>&1 || true; sleep 1; DEV=$(blkid -L "$LABEL" 2>/dev/null || true); fi
if [ -z "$DEV" ]; then
  if [ "${#DISKS[@]}" = 1 ]; then DEV=${DISKS[0]}; else
    mdadm --create /dev/md/lra-scratch --run --force --level=0 --chunk=512 --raid-devices="${#DISKS[@]}" --name=lra-scratch "${DISKS[@]}"
    DEV=/dev/md/lra-scratch; udevadm settle
  fi
  mkfs.ext4 -q -F -L "$LABEL" -E nodiscard,lazy_itable_init=1,lazy_journal_init=1 -m 0 "$DEV"
  echo "scratch: created ext4 on $DEV (${#DISKS[@]} disks)"
fi
mount -o noatime "$DEV" "$MNT"
mkdir -p "$MNT/tmp" "$MNT/cache" "$MNT/work"; chmod 1777 "$MNT/tmp"; chown "$OWNER:$OWNER" "$MNT" "$MNT/cache" "$MNT/work"
echo "scratch: mounted $DEV at $MNT ($(df -h --output=size "$MNT" | tail -1 | tr -d ' '))"
