# 3.12 because it is stable
FROM python:3.12-slim

# Install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# copy files
WORKDIR /app
COPY requirements.txt .

# Run 
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]