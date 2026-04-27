# Multi-stage build to reduce image size
# Stage 1: Builder
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
   libpq-dev \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    libpng-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
  libpq5 \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root app user (security best practice)
RUN useradd -m -u 1000 appuser

# Copy Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY start.sh .

# Set ownership to app user and make start script executable
RUN chown -R appuser:appuser /app && chmod +x /app/start.sh

# Switch to non-root user
USER appuser

# Add local pip packages to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Expose port
EXPOSE 8000

# Health check (runs as appuser)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health').read()"

# Run migrations (with retry) then start application
CMD ["/app/start.sh"]
