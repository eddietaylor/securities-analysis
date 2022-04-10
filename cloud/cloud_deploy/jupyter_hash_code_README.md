# Jupyter Hash Code Generation Instructions

To generate a hash code for the jupyter lab password, run the following:

    python jupyter_hash_code.py "your_password_here"

Then copy this as a string into the jupyter_notebook_config.py file for the variable 
definition of c.NotebookApp.password.