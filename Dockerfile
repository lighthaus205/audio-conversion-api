FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && apt-get install -y ffmpeg

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app /app

# Expose port
EXPOSE 9001

# Run the application
CMD ["uvicorn", "main:app", "--log-level", "debug", "--host", "localhost", "--port", "9001"]