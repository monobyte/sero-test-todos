# Quick Start Guide

Get the Market Monitor backend running in 5 minutes.

## Prerequisites

- Python 3.11 or higher
- pip package manager
- Internet connection (for installing dependencies)

## Installation

### 1. Navigate to Backend Directory
```bash
cd backend
```

### 2. Create Virtual Environment
```bash
python -m venv venv
```

### 3. Activate Virtual Environment

**macOS/Linux:**
```bash
source venv/bin/activate
```

**Windows:**
```cmd
venv\Scripts\activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Configure Environment
```bash
cp .env.example .env
```

**Note:** The server will run without API keys, but external data sources won't work until you add them.

## Running the Server

### Option 1: Using the Convenience Script (Recommended)
```bash
./run.sh
```

This script will:
- Check for virtual environment
- Install dependencies
- Check for .env file
- Start the server with auto-reload

### Option 2: Manual Start
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Option 3: Using Python Directly
```bash
python main.py
```

## Accessing the API

Once running, the API is available at:

- **API Base**: http://0.0.0.0:8000
- **Interactive Docs**: http://0.0.0.0:8000/docs
- **ReDoc**: http://0.0.0.0:8000/redoc
- **Health Check**: http://0.0.0.0:8000/health

## Test the API

### Using curl
```bash
# Health check
curl http://0.0.0.0:8000/health

# Cache stats
curl http://0.0.0.0:8000/health/cache

# Rate limits
curl http://0.0.0.0:8000/health/rate-limits
```

### Using Browser
Navigate to http://0.0.0.0:8000/docs for interactive API documentation.

## Expected Health Check Response

```json
{
  "status": "healthy",
  "timestamp": "2026-03-06T14:00:00Z",
  "version": "0.1.0",
  "environment": "development",
  "services": {
    "finnhub": false,
    "fmp": false,
    "alpha_vantage": false,
    "twelve_data": false,
    "coingecko": false
  }
}
```

All services will show `false` until you add API keys to `.env`.

## Adding API Keys (Optional)

### 1. Sign Up for Free Tiers

**Stock Data:**
- Finnhub: https://finnhub.io/register
- Financial Modeling Prep: https://site.financialmodelingprep.com/developer/docs

**Crypto Data:**
- CoinGecko: https://www.coingecko.com/en/api/pricing

### 2. Add Keys to .env

Edit `.env` file:
```env
FINNHUB_API_KEY=your_actual_key_here
COINGECKO_API_KEY=your_actual_key_here
FMP_API_KEY=your_actual_key_here
```

### 3. Restart Server

```bash
# Press Ctrl+C to stop
# Then restart
./run.sh
```

## Troubleshooting

### Port Already in Use
```bash
# Kill process on port 8000
lsof -ti:8000 | xargs kill -9

# Or use a different port
uvicorn main:app --host 0.0.0.0 --port 8001
```

### Module Import Errors
```bash
# Verify imports work
python test_imports.py

# Should output:
# ✅ All imports successful!
```

### Virtual Environment Not Activating
```bash
# Recreate virtual environment
rm -rf venv
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

### Missing Dependencies
```bash
# Reinstall all dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

## Next Steps

Once the server is running:

1. **Explore Interactive Docs**
   - Go to http://0.0.0.0:8000/docs
   - Try the `/health` endpoint
   - View the auto-generated API schema

2. **Add API Keys**
   - Sign up for free tiers (see above)
   - Add keys to `.env`
   - Restart server

3. **Monitor Logs**
   - Watch the terminal for structured logs
   - All requests are logged with timing info

4. **Wait for Next Subtask**
   - Service layer implementation
   - Quote endpoints
   - Historical data endpoints

## Development Mode

The server runs with `--reload` flag by default, which means:
- Auto-reloads on code changes
- No need to restart manually
- Hot reload for faster development

## Production Mode

For production deployment:
```bash
# Disable auto-reload
uvicorn main:app --host 0.0.0.0 --port 8000

# Or set environment
export APP_ENV=production
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

## File Structure

```
backend/
├── main.py              # Start here: FastAPI app
├── config.py            # Configuration settings
├── models/              # Data models
├── routers/             # API endpoints
├── services/            # External API integrations (future)
├── utils/               # Cache, rate limiter, logger
└── *.md                 # Documentation
```

## Getting Help

- **README.md**: Comprehensive setup guide
- **ARCHITECTURE.md**: Architecture details
- **API_PROVIDERS.md**: API provider reference
- **SETUP_SUMMARY.md**: Setup completion summary

## Common Commands

```bash
# Start server (dev mode)
./run.sh

# Start server (manual)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Test imports
python test_imports.py

# Install dependencies
pip install -r requirements.txt

# Create .env from template
cp .env.example .env

# Check Python version
python --version  # Should be 3.11+
```

---

**Ready to go!** 🚀

Your backend is now running and ready for the next development phase.
