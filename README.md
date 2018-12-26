# aos-vehicle-vm-provisioning
AOS vehicle Virtual Machine provisioning

This repository is the collection of scripts and documentation for
initial provisioning of virtual machine with Ubuntu installed

| Acronym and acronyms | Definition |
|---|---|
| AoS | Solution provided by EPAM responsible for deployment and management embedded applications |
| VM | Virtual Machine |


## Installation steps

### OS and Virtual Machine Requirements

The scripts in this project suppose that you:
 - you are using Ubuntu **Server** (for example 18.04LTS) with all the latest updates
 - virtualization engine (for example, QEMU) was setup and works properly on your workstation
 - you've created virtual machine with latest stable Ubuntu 18.04.
  

_This repository does not include documentation for
setting up virtual machine and OS. Please refer to respective documentations._

### Setup Prerequisities

#### Enable root access to the VM via personal ssh key
Please, refer to respective documentations.
Or execute (works under Ubuntu Server):

```bash
# Load environment variables (PROVIDE variable values in provisioning.sh for your env)
source ./provisioning.sh

# Copy your ssh public key to authorized keys
ssh-copy-id $AOS_VM_USERNAME@$AOS_VEHICLE
ssh $AOS_VM_USERNAME@$AOS_VEHICLE

# On the remote machine copy authorized_keys to root
sudo cp ~/.ssh/authorized_keys /root/.ssh/

# Exit from the VM
exit

# Test connection
ssh root@$AOS_VEHICLE
```

### Setup AOS on VM

Modify ./provisioning.sh to apply your values (IP address of VM) and then run:

```bash
./step01.sh
```

After successful setup reboot VM (to apply changes)
