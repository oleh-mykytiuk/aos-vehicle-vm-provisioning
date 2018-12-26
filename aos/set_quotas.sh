#!/bin/bash

# Read quotas
fstab='/etc/fstab'

# Make backup
bkname="$fstab-backup.$(date +%F_%H%M%S)"
cp "$fstab" "$bkname"

awk -F: '/^[^#]/ {print $1, $2, $3, $4, $5, $6}' $bkname |
while read fstab_fs fstab_mp fstab_type fstab_opt fstab_dump fstab_pass; do
  if [[ $fstab_mp == '/' && $fstab_type =~ "usrquota" ]]; then
    printf "$fstab_fs  $fstab_mp  $fstab_type  $fstab_opt,usrquota  $fstab_dump  $fstab_pass\n"
  else
    printf "$fstab_fs  $fstab_mp  $fstab_type  $fstab_opt  $fstab_dump  $fstab_pass\n"
  fi
done
 > "$fstab"
