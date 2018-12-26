#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
NOC='\033[0m'

AOS_VM_ADDRESS_FILE='~/aos_vm_address'
AOS_BASE_DIR='/var/aos'

function print_colored_text()
{
  echo -e $1
}

function check_hostname()
{
  printf "Trying to connect to AOS vehicle VM..."
  ssh root@$AOS_VEHICLE "echo \"1\" > /dev/null"
  if [[ $? != 0 ]]; then
    print_colored_text "${RED}failed${NOC}"
    return 1
  else
    print_colored_text "${GREEN}OK${NOC}"
    return 0
  fi
}


# Check for id_rsa and generate it if needed
if [[ ! -f ~/.ssh/id_rsa ]]; then
  print_colored_text "${GREEN}id_rsa${NOC} is ${RED}not presents${NOC}, generate it!"
  ssh-keygen -q -b 2048 -t rsa -f ~/.ssh/id_rsa
fi


# Ask user for VM ip address and username

set +e
print_colored_text "You will be asked for VirtualMachine ${GREEN}IP${NOC} address and ${GREEN}username${NOC}"
for (( ; ; ))
do
  print_colored_text "Enter ${GREEN}IP address${NOC} of the VirtualMachine (or press Ctrl+C for stop):"
  read AOS_VM_IP
  print_colored_text "Enter ${GREEN}username${NOC} for access to the VirtualMachine:"
  read AOS_VM_USER

  print_colored_text "Trying to copy key to ${GREEN}${AOS_VM_USER}@${AOS_VM_IP}${NOC}. You might be asked for password up to 2 times"
  ssh-copy-id $AOS_VM_USER@$AOS_VM_IP
  if [[ $? != 0 ]]; then
    print_colored_text "${RED}Error coping key${NOC}. Enter values once more time"
    continue
  fi
  ssh $AOS_VM_USER@$AOS_VM_IP "sudo -S cp ~/.ssh/authorized_keys /root/.ssh/"

  rm -f $AOS_VM_ADDRESS_FILE
  echo $AOS_VM_IP >> $AOS_VM_ADDRESS_FILE
  AOS_VEHICLE := $AOS_VM_IP
  print_colored_text "${GREEN}Key successful set${NOC}."
  break
done

set -e
check_hostname

# Update and upgrade ubuntu
print_colored_text "Updating your ${GREEN}Ubuntu${NOC}..."
ssh root@$AOS_VEHICLE "apt update"

set +e
for (( ii=0 ; ii<25 ; ii++ ))
do
  ssh root@$AOS_VEHICLE "apt upgrade -y"
  if [[ $? == 0 ]]; then
    break
  else
    print_colored_text "Sleep for ${GREEN}5${NOC} seconds..."
    sleep 5
  fi
done
set -e

# Install required software
print_colored_text "installing ${GREEN}system software${NOC}..."
ssh root@$AOS_VEHICLE "apt install -y apt-transport-https ca-certificates curl software-properties-common dbus-x11 quota"

# Install docker (and runc)
print_colored_text "Installing ${GREEN}DOCKER${NOC}..."
ssh root@$AOS_VEHICLE "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -"
ssh root@$AOS_VEHICLE "add-apt-repository \"deb [arch=amd64] https://download.docker.com/linux/ubuntu `lsb_release -cs` stable\""
ssh root@$AOS_VEHICLE "apt update"
ssh root@$AOS_VEHICLE "apt install -y docker-ce"

# Check sysctl.ipv4.ip_forward
print_colored_text "Checking ${GREEN}IP forward${NOC}..."
IP_FORWARD_ENABLED=`ssh root@$AOS_VEHICLE "sysctl -n net.ipv4.ip_forward"`
if [[ $IP_FORWARD_ENABLED != 1 ]]; then
  print_colored_text "net.ipv4.ip_forward is ${RED}not${NOC} enabled. ${GREEN}Enable${NOC} it!"
  ssh root@$AOS_VEHICLE "echo \"net.ipv4.ip_forward=1\" >> /etc/sysctl.conf"
  ssh root@$AOS_VEHICLE "sysctl -p"
else
  print_colored_text "net.ipv4.ip_forward is already ${GREEN}enabled${NOC}."
fi

# Disable exit on error
set +e

# Check wwwivi is known host
print_colored_text "Checking ${GREEN}wwwivi${NOC}..."
ssh root@$AOS_VEHICLE "nslookup wwwivi &> /dev/null"
if [[ $? != 0 ]]; then
  print_colored_text "wwwivi is ${RED}unknown${NOC} host. ${GREEN}Add${NOC} it to /etc/hosts!"
  ssh root@$AOS_VEHICLE "echo \"172.19.0.1 wwwivi\" >> /etc/hosts"
else
  print_colored_text "wwwivi ${GREEN}OK${NOC}."
fi

# Enable exit on error
set -e

# Copy files
print_colored_text "Copying files to VM..."
ssh root@$AOS_VEHICLE "mkdir -p ${AOS_BASE_DIR}/servicemanager"
ssh root@$AOS_VEHICLE "mkdir -p ${AOS_BASE_DIR}/vis"
ssh root@$AOS_VEHICLE "mkdir -p /usr/share/telemetry_emulator"
ssh root@$AOS_VEHICLE "mkdir -p /usr/share/ca-certificates/extra/"

rcp -r ./aos/aos_servicemanager/* root@$AOS_VEHICLE:${AOS_BASE_DIR}/servicemanager
rcp -r ./aos/aos_vis/* root@$AOS_VEHICLE:${AOS_BASE_DIR}/vis
rcp -r ./aos/aos_telemetry_emulator/* root@$AOS_VEHICLE:/usr/share/telemetry_emulator
rcp ./aos/set_quotas.sh root@$AOS_VEHICLE:${AOS_BASE_DIR}/set_quotas.sh

# Setup AOS service manager
print_colored_text "Setup ${GREEN}AOS services${NOC}..."
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/servicemanager/aos-servicemanager.service /etc/systemd/system/"
## Copy needed tools
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/servicemanager/aos_servicemanager /usr/bin/"
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/servicemanager/netns /usr/local/bin/"
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/servicemanager/wondershaper /usr/local/bin/"
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/servicemanager/data/fcrypt/rootCA.crt.pem /usr/share/ca-certificates/extra/rootCA.crt"

ROOT_CERT_ENABLED_ENABLED=`ssh root@$AOS_VEHICLE "cat /etc/ca-certificates.conf | grep extra/rootCA.crt | wc -l"`
if [[ $ROOT_CERT_ENABLED_ENABLED != 1 ]]; then
  print_colored_text "Add ${GREEN}AOS${NOC} root CA cert..."
  ssh root@$AOS_VEHICLE "echo \"extra/rootCA.crt\" >> /etc/ca-certificates.conf"
  ssh root@$AOS_VEHICLE "update-ca-certificates"
fi
ssh root@$AOS_VEHICLE "systemctl enable aos-servicemanager.service"

# Setup VIS
print_colored_text "Setup ${GREEN}AOS VIS${NOC}..."
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/vis/aos_vis /usr/bin/"
ssh root@$AOS_VEHICLE "cp ${AOS_BASE_DIR}/vis/aos-vis.service /etc/systemd/system/"
ssh root@$AOS_VEHICLE "systemctl enable aos-vis.service"


# Setup Telemetry emulator
print_colored_text "Setup ${GREEN}AOS telemetry emulator${NOC}..."
ssh root@$AOS_VEHICLE "cp /usr/share/telemetry_emulator/telemetry-emulator.service /etc/systemd/system/"
ssh root@$AOS_VEHICLE "systemctl enable telemetry-emulator.service"

# Reload daemons
ssh root@$AOS_VEHICLE "systemctl daemon-reload"

# Setup quotas
print_colored_text "Setup ${GREEN}quotas${NOC}..."
ssh root@$AOS_VEHICLE "bash ${AOS_BASE_DIR}/set_quotas.sh"
ssh root@$AOS_VEHICLE "mount -o remount /"
ssh root@$AOS_VEHICLE "quotacheck -avum && quotaon -avu"

print_colored_text "All ${GREEN}OK${NOC}! Reboot your VM"
