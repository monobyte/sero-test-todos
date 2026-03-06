# Changelog

All notable changes to Market Monitor will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- GET /api/quotes/{symbol} - Real-time quotes endpoint
- GET /api/historical/{symbol} - Historical OHLCV data
- GET /api/screener - Stock/crypto screener
- WebSocket /ws/quotes - Real-time price feeds
- Frontend dashboard with watchlist
- Interactive candlestick charts
- Trading idea generation with technical indicators

## [0.1.0] - 2026-03-06

### Added

#### Backend
- FastAPI application setup with async support
- Health check endpoints (`/health`, `/health/cache`, `/health/rate-limits`)
- Multi-tier caching system (quotes: 60s, historical: 1h, fundamentals: 24h)
- Rate limiting with sliding window algorithm (50 calls/min default)
- Structured logging with contextlog
- Pydantic v2 models for type-safe validation
- CORS middleware for cross-origin requests
- Error handling with standardized error responses
- Environment-based configuration via .env
- Comprehensive test suite (pytest + httpx)
  - Integration tests for health endpoints
  - Unit tests for cache manager
  - Unit tests for rate limiter
  - Unit tests for Pydantic models

#### Frontend
- Vite + React 19 + TypeScript setup
- TailwindCSS 4 integration
- Component testing with Vitest + Testing Library
- ESLint configuration
- Hot Module Replacement (HMR) for fast development

#### Documentation
- README.md with architecture diagram (Mermaid)
- API key acquisition guide for all free-tier providers
- Caching strategy documentation
- Rate limiting strategy documentation
- TESTING.md - Comprehensive testing guide
- DEPLOYMENT.md - Production deployment guide
- API_DOCUMENTATION.md - Complete API reference
- CONTRIBUTING.md - Development workflow guide
- Frontend README.md
- Backend README.md with detailed setup instructions

#### Infrastructure
- pytest configuration with coverage reporting
- Vitest configuration for frontend tests
- Docker-ready structure (Dockerfiles coming soon)
- systemd service template for production
- nginx configuration template
- GitHub Actions workflow templates (coming soon)

### Configuration
- Environment variable management with Pydantic Settings
- .env.example with all required API keys
- Separate development/production configs

### Developer Experience
- Automatic API documentation at /docs (Swagger UI)
- ReDoc API documentation at /redoc
- OpenAPI specification at /openapi.json
- Structured logging with contextual information
- Type hints throughout codebase
- Test fixtures for common scenarios

### Security
- CORS configuration
- Rate limiting to prevent abuse
- Secrets management best practices documented
- HTTPS setup guide with Let's Encrypt

## [0.0.1] - 2026-03-01

### Added
- Initial project structure
- Basic Python/Node.js setup
- Git repository initialization

---

## Version History

### Versioning Scheme

- **MAJOR.MINOR.PATCH** (Semantic Versioning)
- **MAJOR:** Breaking changes
- **MINOR:** New features (backward compatible)
- **PATCH:** Bug fixes (backward compatible)

### Release Process

1. Update CHANGELOG.md
2. Update version in:
   - `backend/main.py` (FastAPI app)
   - `frontend/package.json`
3. Commit: `git commit -m "chore: bump version to X.Y.Z"`
4. Tag: `git tag -a vX.Y.Z -m "Release vX.Y.Z"`
5. Push: `git push && git push --tags`

---

## Future Milestones

### v0.2.0 - Data Integration
- [ ] Finnhub service implementation
- [ ] CoinGecko service implementation
- [ ] yfinance fallback service
- [ ] FMP fundamentals service
- [ ] GET /api/quotes/{symbol}
- [ ] GET /api/quotes/batch
- [ ] Caching integration

### v0.3.0 - Historical Data
- [ ] GET /api/historical/{symbol}
- [ ] Support for 1d, 1h, 15m intervals
- [ ] Historical data caching
- [ ] Date range filtering

### v0.4.0 - Frontend UI
- [ ] Dashboard component
- [ ] Watchlist component with add/remove
- [ ] Quote cards with live updates
- [ ] Responsive grid layout
- [ ] Dark mode support

### v0.5.0 - Charts
- [ ] Candlestick chart with Recharts/Lightweight Charts
- [ ] Interactive zoom and pan
- [ ] Multiple timeframes
- [ ] Technical indicators overlay (SMA, EMA)

### v0.6.0 - WebSocket
- [ ] WebSocket server for live quotes
- [ ] Frontend WebSocket client
- [ ] Subscribe/unsubscribe to symbols
- [ ] Connection management and reconnection

### v0.7.0 - Screener
- [ ] GET /api/screener endpoint
- [ ] Filter by price, volume, % change
- [ ] POST /api/screener/technical
- [ ] RSI, MACD, SMA crossover indicators
- [ ] Frontend screener UI

### v0.8.0 - Trading Ideas
- [ ] Automated screening jobs
- [ ] Trading signal generation
- [ ] Idea cards with rationale
- [ ] Backtest results

### v0.9.0 - Polish
- [ ] User preferences storage
- [ ] Price alerts
- [ ] Export watchlist
- [ ] Performance optimizations

### v1.0.0 - Production Ready
- [ ] Full test coverage (90%+)
- [ ] Production deployment guide
- [ ] Monitoring and logging
- [ ] Error tracking (Sentry)
- [ ] Rate limiting dashboard
- [ ] Database for historical storage (optional)

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and guidelines.

## License

Personal use only. See [README.md](README.md) for details.
