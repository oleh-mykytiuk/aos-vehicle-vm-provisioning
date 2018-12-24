#!/bin/bash

set -e

# load variables
source ./provisioning.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
NOC='\033[0m'

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


check_hostname

## Update and upgrade ubuntu
#print_colored_text "Updating your ${GREEN}Ubuntu${NOC}..."
#ssh root@$AOS_VEHICLE "apt update && apt upgrade -y"
#
## Install required software
#print_colored_text "installing ${GREEN}system software${NOC}..."
#ssh root@$AOS_VEHICLE "apt install -y apt-transport-https ca-certificates curl software-properties-common dbus-x11"
#
## Install docker
#print_colored_text "Installing ${GREEN}DOCKER${NOC}..."
#ssh root@$AOS_VEHICLE "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | apt-key add -"
#ssh root@$AOS_VEHICLE "add-apt-repository \"deb [arch=amd64] https://download.docker.com/linux/ubuntu `lsb_release -cs` stable\""
#ssh root@$AOS_VEHICLE "apt update"
#ssh root@$AOS_VEHICLE "apt install -y docker-ce"

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

  set -e

  # Check wwwivi once again
  ssh root@$AOS_VEHICLE "nslookup wwwivi &> /dev/null"
else
  print_colored_text "wwwivi ${GREEN}OK${NOC}."
fi

# Enable exit on error
set -e

# Check wwwivi is known host
print_colored_text "Setup ${GREEN}AOS services${NOC}..."
ssh root@$AOS_VEHICLE "mkdir -p /opt/aos_servicemanager/data/fcrypt"
ssh root@$AOS_VEHICLE "mkdir -p /usr/share/ca-certificates/extra/"
rcp -r ./aos/aos_servicemanager/* root@$AOS_VEHICLE:/opt/aos_servicemanager
ssh root@$AOS_VEHICLE "cp /opt/aos_servicemanager/aos_servicemanager.service /etc/systemd/system/"
## Copy needed tools
ssh root@$AOS_VEHICLE "cp /opt/aos_servicemanager/netns /usr/local/bin/"
ssh root@$AOS_VEHICLE "cp /opt/aos_servicemanager/wondershaper /usr/local/bin/"
ssh root@$AOS_VEHICLE "cp /opt/aos_servicemanager/data/fcrypt/rootCA.crt.pem /usr/share/ca-certificates/extra/rootCA.crt"
ROOT_CERT_ENABLED_ENABLED=`ssh root@$AOS_VEHICLE "cat /etc/ca-certificates.conf | grep extra/rootCA.crt | wc -l"`
if [[ $ROOT_CERT_ENABLED_ENABLED != 1 ]]; then
  print_colored_text "Add ${GREEN}AOS${NOC} root CA cert..."
  ssh root@$AOS_VEHICLE "echo \"extra/rootCA.crt\" >> /etc/ca-certificates.conf"
  ssh root@$AOS_VEHICLE "update-ca-certificates"
fi
ssh root@$AOS_VEHICLE "systemctl enable aos_servicemanager.service"
