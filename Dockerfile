# Use official lightweight Python image
FROM python:3.11-slim

# Install system dependencies: ffmpeg, fontconfig, and system fonts
RUN apt-get update && apt-get install -y \
    ffmpeg \
    fontconfig \
    fonts-dejavu-core \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Rebuild font cache
RUN fc-cache -fv

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Cloud Run injects the PORT environment variable
ENV PORT=8080

# Command to run gunicorn server (15 min timeout for video generation)
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 900 main:app
