# Use the official Python image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy project files into the container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 5000
EXPOSE 5001

# Command to run the Flask app
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
