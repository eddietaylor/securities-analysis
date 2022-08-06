#!/bin/bash

# IP address from first argument
CLOUD_IP=$1

# SSH copy the installation bash script, keys, and config file to cloud
scp dependencies_install.sh root@${CLOUD_IP}:
scp mycert.pem mykey.key jupyter_notebook_config.py ../../environment.yml root@${CLOUD_IP}:
scp ../../data/hash.cfg root@${CLOUD_IP}:

# Execute the dependencies installation
ssh root@${CLOUD_IP} bash /root/dependencies_install.sh