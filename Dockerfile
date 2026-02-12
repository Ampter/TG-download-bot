FROM python:3.12-slim

# Install ffmpeg, curl, and unzip (needed to install Deno)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno (a fast JS runtime for yt-dlp)
RUN curl -fsSL https://deno.land | sh
ENV DENO_INSTALL="/root/.deno"
ENV PATH="$DENO_INSTALL/bin:$PATH"

WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the app
COPY . .

# Create downloads folder
RUN mkdir -p downloads && chmod 777 downloads

CMD ["python", "main.py"]
