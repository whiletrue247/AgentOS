# Base image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV WORKDIR=/app

# Create working directory
WORKDIR $WORKDIR

# Install system dependencies (for building some python packages if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies first (to leverage Docker cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose Dashboard Port
EXPOSE 8080

# Run the OS (default to terminal mode, but can be overridden)
CMD ["python", "main.py"]
