#!/bin/bash

# Linux Software Updates
apt-get update  # updates the package index cache
apt-get upgrade -y  # updates packages
# install system tools
apt-get install -y gcc git htop  # system tools
apt-get install -y screen vim wget  # system tools
apt install -y python3-pip # need pip too
apt-get upgrade -y bash  # upgrades bash if necessary
apt-get clean  # cleans up the package index cache

# allow traffic on this port
sudo ufw allow 9000

# Retrive Miniconda install file and output to Miniconda.sh file
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
		-O Miniconda.sh
# Installs miniconda (-b is without intervention, update an existing installation)
bash Miniconda.sh -b -u 
# Remove the installer
rm -rf Miniconda.sh
# prepends the new path for current session
export PATH="/root/miniconda3/bin:$PATH"
# prepends the new path in the shell configuration
cat >> ~/.bashrc <<EOF
export PATH="/root/miniconda3/bin:$PATH"
EOF

# Install Pip
pip install --upgrade pip 

# Source the Conda command
#source ~/miniconda3/etc/profile.d/conda.sh
echo ". ~/miniconda3/etc/profile.d/conda.sh" >> ~/.bashrc
echo "conda activate" >> ~/.bashrc

# Source the bashrc file
source ~/.bashrc

# Update Conda
conda update -n base -c defaults conda -y

# Install mamba for parallel dependency solver
conda install -y mamba -n base -c conda-forge

# Install Virtual Environment
mamba env create -f environment.yml

# Activate Virtual Environment (no need to)
#conda activate securities-analysis

# Install jupyterlab
conda install -y jupyterlab  # Jupyter Lab environment

# Move config files and keys to correct locations
mkdir /root/.jupyter
mkdir /root/data
mv /root/jupyter_notebook_config.py /root/.jupyter/
mv /root/mycert.pem /root/.jupyter
mv /root/mykey.key /root/.jupyter
mv /root/hash.cfg /root/data
mkdir /root/notebook
cd /root/notebook

# Start jupyter lab server and set password equal to what was set locally
jupyter lab --NotebookApp.password="$(python -c 'import configparser;config=configparser.ConfigParser();config.read("../data/hash.cfg");print(config["jupyterlabserver"]["hash_password"])')" &
