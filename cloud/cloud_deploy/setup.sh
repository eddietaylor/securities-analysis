#!/bin/bash

# IP ADDRESS FROM PARAMETER
MASTER_IP=$1

# COPYING THE FILES
scp dependencies_install.sh root@${MASTER_IP}:
scp mycert.pem mykey.key jupyter_notebook_config.py ../../environment.yml root@${MASTER_IP}:

# EXECUTING THE INSTALLATION SCRIPT
ssh root@${MASTER_IP} bash /root/install.sh