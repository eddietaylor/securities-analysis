#!/bin/bash

# GENERAL LINUX
apt-get update  # updates the package index cache
apt-get upgrade -y  # updates packages
# install system tools
apt-get install -y gcc git htop  # system tools
apt-get install -y screen htop vim wget  # system tools
apt install -y python3-pip # need pip too
apt-get upgrade -y bash  # upgrades bash if necessary
apt-get clean  # cleans up the package index cache

# ALLOW TRAFFIC ON PORT
sudo ufw allow 9000

# INSTALLING MINICONDA
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
		-O Miniconda.sh
bash Miniconda.sh -b  # installs Miniconda
rm -rf Miniconda.sh  # removes the installer
# prepends the new path for current session
export PATH="/root/miniconda3/bin:$PATH"
# prepends the new path in the shell configuration
cat >> ~/.profile <<EOF
export PATH="/root/miniconda3/bin:$PATH"
EOF

# upgrading pip
pip install --upgrade pip 

# Source the Conda command
source ~/miniconda3/etc/profile.d/conda.sh

# install mamba for parallel dependency solver
conda install mamba -n base -c conda-forge

# INSTALLING PYTHON LIBRARIES
mamba env create -f environment.yml

# ACTIVATE VIRTUAL ENVIRONMENT
conda activate securities-analysis

# INSTALLING PYTHON LIBRARIES
conda install -y jupyterlab  # Jupyter Lab environment

# COPYING FILES AND CREATING DIRECTORIES
mkdir /root/.jupyter
mkdir /root/data
mv /root/jupyter_notebook_config.py /root/.jupyter/
mv /root/mycert.pem /root/.jupyter
mv /root/mykey.key /root/.jupyter
mv /root/hash.cfg /root/data
mkdir /root/notebook
cd /root/notebook

# STARTING JUPYTER LAB
jupyter lab --NotebookApp.password="$(python -c 'import configparser;config=configparser.ConfigParser();config.read("../data/hash.cfg");print(config["jupyterlabserver"]["hash_password"])')" &