# Use the official Python image
FROM python:3.9-slim

# Install curl and other dependencies
RUN apt-get update && apt-get install -y curl libpq-dev gcc

# Set the working directory
WORKDIR /app

# Copy project files into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly upgrade psycopg2-binary
RUN pip install --no-cache-dir --upgrade psycopg2-binary

# Expose port 5001
EXPOSE 5001

# Command to run the Flask app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5001"]