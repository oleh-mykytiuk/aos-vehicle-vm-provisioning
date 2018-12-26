#!/bin/bash

source ./vm_env_vars.sh


if [[ ! -f ~/.ssh/id_rsa ]]; then
  echo "id_rsa is not presents, generate it!"
  ssh-keygen -q -b 2048 -t rsa -f ~/.ssh/id_rsa
fi

ssh-copy-id $AOS_VM_USERNAME@$AOS_VEHICLE
ssh $AOS_VM_USERNAME@$AOS_VEHICLE "sudo -S cp ~/.ssh/authorized_keys /root/.ssh/"
