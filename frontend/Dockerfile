# Frontend Dockerfile for React Application
FROM node:20-alpine

# Accept build arguments for environment variables
ARG VITE_API_URL=http://localhost:8000
ARG VITE_GOOGLE_CLIENT_ID
ARG VITE_DISABLE_AUTH=true

# Set working directory
WORKDIR /app

# Copy package.json only (let npm generate fresh package-lock.json)
COPY package.json ./

# Clear npm cache and install all dependencies (including dev dependencies for build)
RUN npm cache clean --force && npm install

# Copy source code
COPY . .

# Set environment variables for build
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
ENV VITE_DISABLE_AUTH=$VITE_DISABLE_AUTH

# Build the application
RUN npm run build

# Install serve to run the production build
RUN npm install -g serve

# Expose port
EXPOSE 8503

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8503 || exit 1

# Start the application
CMD ["serve", "-s", "dist", "-l", "8503"]
