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

The scripts in this project suppose that you have Ubuntu Server 18.04LTS
 with all the latest updates running either natively or in some virtualization engine
 (e.g. VirtualBox, Parallels, QEMU) on your workstation
  

_This repository does not include documentation for
setting up virtual machine and OS. Please refer to respective documentations._

### Setup Prerequisities

#### Enable root access to the VM via personal ssh key
Please, refer to respective documentations.
Or execute (you'll be asked for your user password 2 times to access to VM):

```bash
# Load environment variables 
#  (do not forget to PROVIDE values in vm_env_vars.sh for your env:
#    IP address and user

./step00.sh
```

### Setup AOS on VM

Modify ./vm_env_vars.sh to apply your values (IP address of VM) and then run:

```bash
./step01.sh
```

After successful setup reboot VM (to apply changes)
