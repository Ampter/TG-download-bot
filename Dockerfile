# Stage 1: Get the Deno binary (still useful for yt-dlp)
FROM denoland/deno:bin-2.1.9 AS deno_binary

# Stage 2: Build your Python app
FROM python:3.12-slim

# Install ffmpeg, curl, and Node.js (required for the provider)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Copy Deno
COPY --from=deno_binary /deno /usr/local/bin/deno

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Clone and build the bgutil provider (HTTP server)
RUN git clone --single-branch --branch 1.2.2 https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git /opt/provider
WORKDIR /opt/provider/server
RUN npm install && npx tsc

# Go back to app directory
WORKDIR /app

# Copy the rest of your app
COPY . .

# Create downloads folder
RUN mkdir -p downloads && chmod 777 downloads

# Copy a startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Set environment for Deno
ENV PATH="/usr/local/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Expose the provider port (optional, for external checks)
EXPOSE 4416

CMD ["/start.sh"]
