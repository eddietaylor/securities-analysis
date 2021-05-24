#!/bin/bash
#
# Script to install
# Linux system tools
# and basic Python 
# components

# Linux Updates and System Tools
apt-get update
apt-get upgrade -y
apt-get install -y bzip2 gcc git
apt-get install -y htop screen vim wget
apt-get upgrade -y bash 
apt-get clean

# Install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O Miniconda.sh
bash Miniconda.sh -b
rm -rf Miniconda.sh
export PATH="/root/miniconda3/bin:$PATH"

# Install Python libraries
conda install -y pandas
conda install -y ipython

cd /root/
wget http://hilpisch.com/.vimrc
