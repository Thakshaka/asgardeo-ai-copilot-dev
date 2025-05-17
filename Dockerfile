FROM python:3.10-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Set environment variables
ENV PYTHONPATH=/app

# Create a non-root user and switch to it
RUN adduser \
    --disabled-password \
    --gecos "" \
    --home "/nonexistent" \
    --shell "/sbin/nologin" \
    --no-create-home \
    --uid 10014 \
    "choreo" && \
    chown -R 10014:10014 /app

USER 10014

# Run the docs_db_updater
CMD ["python", "-m", "docs_db_updater.application.main"]
