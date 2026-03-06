# Deployment Guide

Comprehensive deployment guide for Market Monitor application covering local development, production deployment, cloud platforms, and Docker.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Local Development](#local-development)
- [Production Deployment](#production-deployment)
  - [Linux Server (systemd)](#linux-server-systemd)
  - [Docker Compose](#docker-compose)
  - [Cloud Platforms](#cloud-platforms)
- [Environment Configuration](#environment-configuration)
- [Security Best Practices](#security-best-practices)
- [Monitoring & Logging](#monitoring--logging)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

| Component | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| npm | 9+ | Frontend package manager |
| Git | 2.x | Version control |

### Optional (for production)

- **nginx** or **Caddy** — Reverse proxy
- **systemd** — Service management (Linux)
- **Docker** — Containerization
- **PostgreSQL** — Database (future enhancement)
- **Redis** — Distributed caching (multi-instance)

---

## Local Development

### Backend (Development Mode)

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add API keys (see README.md)

# Run with auto-reload
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

**Access:**
- API: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

### Frontend (Development Mode)

```bash
cd frontend

# Install dependencies
npm install

# Run dev server (Vite with HMR)
npm run dev
```

**Access:**
- Frontend: http://localhost:3000 (or port shown in terminal)
- HMR enabled (instant updates on save)

### Running Both Simultaneously

**Option 1: Two terminals**

Terminal 1:
```bash
cd backend && uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2:
```bash
cd frontend && npm run dev
```

**Option 2: tmux/screen (Linux/macOS)**

```bash
# Install tmux
sudo apt install tmux  # Ubuntu/Debian
brew install tmux      # macOS

# Start tmux session
tmux new -s market-monitor

# Split window: Ctrl+B then "
# Switch panes: Ctrl+B then arrow keys
# In pane 1: cd backend && uvicorn main:app --reload
# In pane 2: cd frontend && npm run dev

# Detach: Ctrl+B then D
# Reattach: tmux attach -t market-monitor
```

**Option 3: npm-run-all (coming soon)**

Create root `package.json`:

```json
{
  "scripts": {
    "dev": "npm-run-all --parallel dev:backend dev:frontend",
    "dev:backend": "cd backend && uvicorn main:app --reload",
    "dev:frontend": "cd frontend && npm run dev"
  }
}
```

---

## Production Deployment

### Linux Server (systemd)

#### 1. Setup Server

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.11 python3.11-venv nginx

# Install Node.js 18
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Create application user
sudo useradd -m -s /bin/bash marketmonitor
sudo usermod -aG www-data marketmonitor
```

#### 2. Deploy Application

```bash
# Clone repository
sudo mkdir -p /var/www
sudo chown marketmonitor:marketmonitor /var/www
sudo -u marketmonitor git clone <repo-url> /var/www/market-monitor
cd /var/www/market-monitor

# Backend setup
cd backend
sudo -u marketmonitor python3.11 -m venv venv
sudo -u marketmonitor ./venv/bin/pip install -r requirements.txt

# Configure environment
sudo -u marketmonitor cp .env.example .env
sudo -u marketmonitor nano .env  # Add production API keys

# Frontend build
cd ../frontend
sudo -u marketmonitor npm ci
sudo -u marketmonitor npm run build
```

#### 3. Create systemd Service

Create `/etc/systemd/system/market-monitor-api.service`:

```ini
[Unit]
Description=Market Monitor FastAPI Backend
After=network.target

[Service]
Type=simple
User=marketmonitor
Group=marketmonitor
WorkingDirectory=/var/www/market-monitor/backend
Environment="PATH=/var/www/market-monitor/backend/venv/bin"
ExecStart=/var/www/market-monitor/backend/venv/bin/uvicorn main:app \
    --host 127.0.0.1 \
    --port 8000 \
    --workers 4
Restart=always
RestartSec=10

# Security
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/www/market-monitor/backend

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=market-monitor-api

[Install]
WantedBy=multi-user.target
```

Enable and start service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable market-monitor-api
sudo systemctl start market-monitor-api
sudo systemctl status market-monitor-api
```

#### 4. Configure nginx

Create `/etc/nginx/sites-available/market-monitor`:

```nginx
# Rate limiting
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=static_limit:10m rate=50r/s;

server {
    listen 80;
    server_name market-monitor.example.com;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # Frontend (React build)
    location / {
        root /var/www/market-monitor/frontend/dist;
        try_files $uri $uri/ /index.html;
        
        # Rate limit static files
        limit_req zone=static_limit burst=20 nodelay;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # Backend API
    location /api {
        # Rate limit API calls
        limit_req zone=api_limit burst=20 nodelay;
        
        proxy_pass http://127.0.0.1:8000/api;
        proxy_http_version 1.1;
        
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # WebSocket
    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;
        
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        
        # WebSocket timeouts
        proxy_connect_timeout 7d;
        proxy_send_timeout 7d;
        proxy_read_timeout 7d;
    }

    # Health check endpoint (no rate limit)
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }

    # API docs
    location /docs {
        proxy_pass http://127.0.0.1:8000/docs;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000/openapi.json;
    }
}
```

Enable site:

```bash
sudo ln -s /etc/nginx/sites-available/market-monitor /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

#### 5. Setup HTTPS (Let's Encrypt)

```bash
# Install Certbot
sudo apt install -y certbot python3-certbot-nginx

# Obtain certificate
sudo certbot --nginx -d market-monitor.example.com

# Auto-renewal (already set up by Certbot)
sudo systemctl status certbot.timer
```

nginx will be automatically updated to:

```nginx
server {
    listen 443 ssl http2;
    server_name market-monitor.example.com;

    ssl_certificate /etc/letsencrypt/live/market-monitor.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/market-monitor.example.com/privkey.pem;
    
    # ... rest of config
}

server {
    listen 80;
    server_name market-monitor.example.com;
    return 301 https://$server_name$request_uri;
}
```

---

### Docker Compose

#### 1. Create Dockerfiles

**Backend Dockerfile** (`backend/Dockerfile`):

```dockerfile
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Frontend Dockerfile** (`frontend/Dockerfile`):

```dockerfile
# Build stage
FROM node:18-alpine AS build

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source
COPY . .

# Build application
RUN npm run build

# Production stage
FROM nginx:alpine

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=build /app/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost/health || exit 1

# Run nginx
CMD ["nginx", "-g", "daemon off;"]
```

**Frontend nginx.conf** (`frontend/nginx.conf`):

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    # Gzip compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # SPA routing
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Health check
    location /health {
        access_log off;
        return 200 "healthy\n";
        add_header Content-Type text/plain;
    }
}
```

#### 2. Create docker-compose.yml

**Root `docker-compose.yml`**:

```yaml
version: '3.8'

services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    container_name: market-monitor-api
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - APP_ENV=production
      - APP_HOST=0.0.0.0
      - APP_PORT=8000
      - CORS_ORIGINS=http://localhost:3000,https://market-monitor.example.com
    env_file:
      - ./backend/.env
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s
    networks:
      - market-monitor-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: market-monitor-frontend
    restart: unless-stopped
    ports:
      - "80:80"
    depends_on:
      backend:
        condition: service_healthy
    networks:
      - market-monitor-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  market-monitor-network:
    driver: bridge
```

#### 3. Deploy with Docker Compose

```bash
# Build images
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Rebuild and restart
docker-compose up -d --build
```

#### 4. Docker Management

```bash
# View running containers
docker-compose ps

# Restart specific service
docker-compose restart backend

# View backend logs
docker-compose logs -f backend

# Execute command in container
docker-compose exec backend bash

# Scale services (if configured)
docker-compose up -d --scale backend=3

# Remove all containers and volumes
docker-compose down -v
```

---

### Cloud Platforms

#### Vercel (Frontend Only)

**Recommended for:** Frontend hosting with global CDN

```bash
cd frontend

# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy preview
vercel

# Deploy to production
vercel --prod
```

**`vercel.json` configuration:**

```json
{
  "builds": [
    {
      "src": "package.json",
      "use": "@vercel/static-build",
      "config": {
        "distDir": "dist"
      }
    }
  ],
  "routes": [
    {
      "src": "/(.*)",
      "dest": "/index.html"
    }
  ]
}
```

**Environment variables:**

Set in Vercel dashboard:
- `VITE_API_URL` → Backend API URL (e.g., `https://api.market-monitor.com`)

---

#### Railway (Backend + Frontend)

**Recommended for:** Full-stack deployment with minimal config

**Create `railway.toml`:**

```toml
[build]
builder = "NIXPACKS"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/health"
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 10

[env]
APP_ENV = "production"
```

**Deploy:**

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Deploy
railway up
```

**Add environment variables in Railway dashboard:**
- All API keys from `.env`
- `CORS_ORIGINS` → Frontend URL

---

#### Render

**`render.yaml`:**

```yaml
services:
  # Backend
  - type: web
    name: market-monitor-api
    env: python
    region: oregon
    plan: free
    buildCommand: "pip install -r requirements.txt"
    startCommand: "uvicorn main:app --host 0.0.0.0 --port $PORT"
    healthCheckPath: /health
    envVars:
      - key: APP_ENV
        value: production
      - key: FINNHUB_API_KEY
        sync: false  # Set in dashboard
      - key: COINGECKO_API_KEY
        sync: false
      - key: FMP_API_KEY
        sync: false

  # Frontend
  - type: web
    name: market-monitor-frontend
    env: static
    region: oregon
    plan: free
    buildCommand: "npm install && npm run build"
    staticPublishPath: ./dist
    routes:
      - type: rewrite
        source: /*
        destination: /index.html
```

**Deploy:**

1. Push to GitHub
2. Connect repository in Render dashboard
3. Render auto-deploys on push

---

#### Google Cloud Run

**Backend deployment:**

```bash
# Build and push image
gcloud builds submit --tag gcr.io/PROJECT_ID/market-monitor-api backend/

# Deploy
gcloud run deploy market-monitor-api \
  --image gcr.io/PROJECT_ID/market-monitor-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars APP_ENV=production \
  --set-secrets FINNHUB_API_KEY=FINNHUB_API_KEY:latest
```

**Frontend deployment:**

```bash
# Build
cd frontend
npm run build

# Deploy to Cloud Storage + Cloud CDN
gsutil -m rsync -r -d dist gs://BUCKET_NAME

# Enable CDN
gcloud compute backend-buckets create market-monitor-frontend-bucket \
  --gcs-bucket-name=BUCKET_NAME \
  --enable-cdn
```

---

## Environment Configuration

### Production Environment Variables

**Backend `.env` (production):**

```bash
# Application
APP_ENV=production
APP_HOST=0.0.0.0
APP_PORT=8000
LOG_LEVEL=WARNING

# CORS (adjust to your domain)
CORS_ORIGINS=https://market-monitor.example.com

# API Keys (use secrets management in production)
FINNHUB_API_KEY=<from_secrets_manager>
COINGECKO_API_KEY=<from_secrets_manager>
FMP_API_KEY=<from_secrets_manager>

# Cache (production tuning)
CACHE_TTL_QUOTES=60
CACHE_TTL_HISTORICAL=3600
CACHE_TTL_FUNDAMENTALS=86400

# Rate Limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_CALLS_PER_MINUTE=50

# WebSocket
WS_PING_INTERVAL=30
WS_PING_TIMEOUT=10
WS_MAX_CONNECTIONS=100
```

### Secrets Management

**Never commit API keys to Git!**

#### Option 1: Environment Variables

```bash
# Set environment variables in systemd
sudo systemctl edit market-monitor-api

# Add:
[Service]
Environment="FINNHUB_API_KEY=your_key_here"
Environment="COINGECKO_API_KEY=your_key_here"
```

#### Option 2: Docker Secrets

```yaml
# docker-compose.yml
services:
  backend:
    secrets:
      - finnhub_api_key
      - coingecko_api_key

secrets:
  finnhub_api_key:
    file: ./secrets/finnhub_api_key.txt
  coingecko_api_key:
    file: ./secrets/coingecko_api_key.txt
```

#### Option 3: Cloud Secrets Manager

**AWS Secrets Manager:**

```python
import boto3

def get_secret(secret_name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=secret_name)
    return response['SecretString']
```

**Google Cloud Secret Manager:**

```python
from google.cloud import secretmanager

def get_secret(project_id, secret_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")
```

---

## Security Best Practices

### 1. Use HTTPS

```bash
# Let's Encrypt (free)
sudo certbot --nginx -d market-monitor.example.com

# Or use Cloudflare (free tier includes SSL)
```

### 2. Set Security Headers

Add to nginx config:

```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "no-referrer-when-downgrade" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
```

### 3. Rate Limiting

Already implemented in backend, but add nginx rate limiting too:

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

location /api {
    limit_req zone=api_limit burst=20 nodelay;
    limit_req_status 429;
    proxy_pass http://localhost:8000/api;
}
```

### 4. Firewall

```bash
# UFW (Ubuntu)
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

### 5. Regular Updates

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# Python packages
pip install --upgrade pip
pip list --outdated
pip install --upgrade <package>

# Node packages
npm outdated
npm update
```

---

## Monitoring & Logging

### Application Logs

**View systemd logs:**

```bash
# Follow logs
sudo journalctl -u market-monitor-api -f

# Last 100 lines
sudo journalctl -u market-monitor-api -n 100

# Since yesterday
sudo journalctl -u market-monitor-api --since yesterday

# Errors only
sudo journalctl -u market-monitor-api -p err
```

**View Docker logs:**

```bash
docker-compose logs -f backend
docker-compose logs --tail=100 backend
```

### Health Monitoring

**Uptime monitoring:**

Use services like:
- UptimeRobot (free)
- StatusCake (free tier)
- Pingdom (paid)

Monitor: `https://market-monitor.example.com/health`

**Custom health check script:**

```bash
#!/bin/bash
# /usr/local/bin/health-check.sh

HEALTH_URL="http://localhost:8000/health"
RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" $HEALTH_URL)

if [ $RESPONSE -ne 200 ]; then
    echo "Health check failed! Status: $RESPONSE"
    sudo systemctl restart market-monitor-api
    echo "Service restarted"
fi
```

**Cron job:**

```bash
# Check every 5 minutes
*/5 * * * * /usr/local/bin/health-check.sh
```

### Performance Monitoring

**Add monitoring endpoint:**

```python
# backend/routers/metrics.py
from fastapi import APIRouter
import psutil

router = APIRouter(prefix="/metrics", tags=["Metrics"])

@router.get("/system")
async def system_metrics():
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage('/').percent,
    }
```

---

## Troubleshooting

### Backend Won't Start

**Check logs:**

```bash
sudo journalctl -u market-monitor-api -n 50
```

**Common issues:**

1. **Port already in use:**
   ```bash
   sudo lsof -i :8000
   sudo kill -9 <PID>
   ```

2. **Missing dependencies:**
   ```bash
   cd backend
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Permission errors:**
   ```bash
   sudo chown -R marketmonitor:marketmonitor /var/www/market-monitor
   ```

### Frontend 404 on Refresh

**nginx config missing SPA fallback:**

```nginx
location / {
    try_files $uri $uri/ /index.html;  # Add this!
}
```

### WebSocket Connection Fails

**Check nginx WebSocket config:**

```nginx
location /ws {
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```

### API Returns 502 Bad Gateway

**Backend not running:**

```bash
sudo systemctl status market-monitor-api
sudo systemctl restart market-monitor-api
```

**Wrong proxy_pass:**

Check nginx config: `proxy_pass http://127.0.0.1:8000;`

---

**Deployment Complete! 🚀**
