# Build a Docker Image
# with the latest Ubuntu
# and Python install

# parent image
FROM ubuntu:latest

LABEL maintainer="Eddie Taylor"

# copy shell script from local contect
# to root directory of image
ADD system_install.sh /
# change permissions (for owner of file) of scripts
RUN chmod u+x /system_install.sh
# run it
RUN /system_install.sh
# set environment path variable
ENV PATH /root/miniconda3/bin:$PATH

# command to execute (IPython) when container is run
CMD ["ipython"]
