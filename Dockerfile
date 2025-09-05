# Use an official Python runtime as a parent image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code
COPY . .

# The PORT environment variable will be provided by App Hosting.
# EXPOSE is not strictly necessary but good for documentation.
EXPOSE 8080

# Run the app using gunicorn.
# The shell form of CMD is used to allow for environment variable substitution for the port.
CMD gunicorn -w 4 -b "0.0.0.0:${PORT}" backend:app
