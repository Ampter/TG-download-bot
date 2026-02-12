# Stage 1: Get the Deno binary
FROM denoland/deno:bin-2.1.9 AS deno_binary

# Stage 2: Build your Python app
FROM python:3.12-slim

# Install ffmpeg and curl (needed for yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Deno from the first stage
COPY --from=deno_binary /deno /usr/local/bin/deno

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Create downloads folder
RUN mkdir -p downloads && chmod 777 downloads

# Set environment for Deno
ENV PATH="/usr/local/bin:$PATH"

CMD ["python", "main.py"]
