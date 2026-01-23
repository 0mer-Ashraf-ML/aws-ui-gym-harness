# FastAPI Task Runner Dockerfile
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Firefox configuration for Docker
ENV MOZ_HEADLESS=1
ENV DISPLAY=:99
ENV MOZ_DISABLE_CONTENT_SANDBOX=1
ENV MOZ_DISABLE_GMP_SANDBOX=1
ENV MOZ_DISABLE_RDD_SANDBOX=1
ENV MOZ_DISABLE_GPU_SANDBOX=1
ENV MOZ_DISABLE_SOCKET_PROCESS_SANDBOX=1
ENV MOZ_DISABLE_UTILITY_SANDBOX=1
ENV MOZ_DISABLE_VR_SANDBOX=1
ENV MOZ_DISABLE_WEBRTC_SANDBOX=1
ENV MOZ_DISABLE_X11_SANDBOX=1

# Set work directory
WORKDIR /app

# Install system dependencies for Firefox
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
        wget \
        gnupg \
        unzip \
        xvfb \
        libnss3 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libxss1 \
        libasound2 \
        libgtk-3-0 \
        libx11-xcb1 \
        libxcursor1 \
        libxi6 \
        libxtst6 \
        libnss3-dev \
        libatk-bridge2.0-dev \
        libasound2-dev \
        libpangocairo-1.0-0 \
        libatk1.0-0 \
        libcairo-gobject2 \
        libgdk-pixbuf-xlib-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Install Firefox ESR (Extended Support Release) for stability
RUN apt-get update \
    && apt-get install -y --no-install-recommends firefox-esr xvfb \
    && rm -rf /var/lib/apt/lists/*

# Start virtual display server for Firefox
RUN echo '#!/bin/bash\nXvfb :99 -screen 0 1920x1080x24 &\nexec "$@"' > /usr/local/bin/entrypoint.sh \
    && chmod +x /usr/local/bin/entrypoint.sh

# Firefox uses GeckoDriver which is automatically managed by Playwright
# No need to install GeckoDriver separately

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
RUN playwright install firefox

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p logs results

# Set permissions for Firefox (if needed)
RUN chmod +x /usr/bin/firefox-esr

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application with virtual display
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
