FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app

# Create a non-root user and switch to it (using UID in Choreo's required range 10000-20000)
RUN addgroup --system --gid 10001 appgroup && \
    adduser --system --uid 10001 --gid 10001 appuser && \
    chown -R appuser:appgroup /app

USER 10001

# Run the docs_db_updater
CMD ["python", "-m", "docs_db_updater.application.main"]
