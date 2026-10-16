FROM python:3.12-slim-bookworm

# Set the working directory in the container
WORKDIR /app

# Add the requirements file to the container
ADD requirements.txt .

# Install the app system dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the source code into the container
COPY . .

# OpenShift runs the container as an arbitrary non-root UID that is a member of
# group 0 (root). Make /app owned by group 0 and group-writable, so that UID can
# create/write runtime files (e.g. the user_data dir). Without this the app
# crashes at startup on `os.makedirs('user_data')` with PermissionError.
RUN chgrp -R 0 /app \
    && chmod -R g=u /app

# Set env variables
ENV PYTHONUNBUFFERED=1

# Command to run the app on container startup
CMD ["python", "-u", "/app/gradio_ui.py"]
