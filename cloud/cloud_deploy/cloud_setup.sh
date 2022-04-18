#!/bin/bash

# IP ADDRESS FROM PARAMETER
CLOUD_IP=$1

# COPYING THE FILES
scp dependencies_install.sh root@${CLOUD_IP}:
scp mycert.pem mykey.key jupyter_notebook_config.py ../../environment.yml root@${CLOUD_IP}:
scp ../../data/hash.cfg root@${CLOUD_IP}:

# EXECUTING THE INSTALLATION SCRIPT
ssh root@${CLOUD_IP} bash /root/dependencies_install.sh