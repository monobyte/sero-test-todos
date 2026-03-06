# Contributing Guide

Thank you for considering contributing to Market Monitor! This guide will help you set up your development environment and understand the development workflow.

## Table of Contents

- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Code Style](#code-style)
- [Testing](#testing)
- [Commit Guidelines](#commit-guidelines)
- [Pull Request Process](#pull-request-process)

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- Git
- Code editor (VS Code recommended)

### Initial Setup

1. **Fork the repository** (if contributing to open source version)

2. **Clone your fork:**

   ```bash
   git clone https://github.com/YOUR_USERNAME/market-monitor.git
   cd market-monitor
   ```

3. **Set up backend:**

   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   # Edit .env and add API keys
   ```

4. **Set up frontend:**

   ```bash
   cd frontend
   npm install
   ```

5. **Run tests to verify setup:**

   ```bash
   # Backend
   cd backend
   pytest

   # Frontend
   cd frontend
   npm test -- --run
   ```

---

## Development Workflow

### Starting the Application

**Option 1: Two Terminals**

Terminal 1 (Backend):
```bash
cd backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Terminal 2 (Frontend):
```bash
cd frontend
npm run dev
```

**Option 2: Using tmux (Linux/macOS)**

```bash
tmux new -s dev
# Split: Ctrl+B then "
# Navigate: Ctrl+B then arrow keys
# In pane 1: cd backend && uvicorn main:app --reload
# In pane 2: cd frontend && npm run dev
```

### Making Changes

1. **Create a feature branch:**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes**

   - Write code
   - Add tests
   - Update documentation

3. **Test your changes:**

   ```bash
   # Backend
   cd backend
   pytest
   pytest --cov=. --cov-report=html

   # Frontend
   cd frontend
   npm test
   npm run lint
   ```

4. **Commit your changes:**

   ```bash
   git add .
   git commit -m "feat: add new screener endpoint"
   ```

5. **Push to your fork:**

   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create a Pull Request**

---

## Code Style

### Backend (Python)

We follow **PEP 8** with some adjustments.

**Style Guidelines:**

- **Line length:** 100 characters (not 79)
- **Imports:** Group by stdlib, third-party, local (separated by blank line)
- **Type hints:** Use for function parameters and return types
- **Docstrings:** Google style for all public functions/classes
- **F-strings:** Prefer over `.format()` or `%`

**Example:**

```python
"""
Module docstring describing what this module does.
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import settings
from utils import get_logger

logger = get_logger(__name__)


class QuoteRequest(BaseModel):
    """Request model for quote endpoint."""

    symbol: str
    source: Optional[str] = None


async def get_quote(symbol: str) -> dict:
    """
    Fetch quote for a symbol.

    Args:
        symbol: Stock ticker or crypto symbol

    Returns:
        Dictionary with quote data

    Raises:
        HTTPException: If symbol not found
    """
    logger.info("fetching_quote", symbol=symbol)

    # Implementation
    quote = await fetch_from_api(symbol)

    return quote
```

**Tools:**

```bash
# Format with black (coming soon)
pip install black
black .

# Lint with flake8 (coming soon)
pip install flake8
flake8 .

# Type check with mypy (coming soon)
pip install mypy
mypy .
```

### Frontend (TypeScript/React)

**Style Guidelines:**

- **Components:** PascalCase, one per file
- **Functions:** camelCase
- **Constants:** UPPER_SNAKE_CASE
- **Interfaces/Types:** PascalCase, prefix interfaces with `I` (optional)
- **Props:** Destructure in function signature
- **Hooks:** Start with `use` prefix

**Example:**

```typescript
// Good component structure
interface QuoteCardProps {
  symbol: string;
  onRefresh?: () => void;
}

export function QuoteCard({ symbol, onRefresh }: QuoteCardProps) {
  const [quote, setQuote] = useState<Quote | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchQuote();
  }, [symbol]);

  async function fetchQuote() {
    try {
      const data = await getQuote(symbol);
      setQuote(data);
    } catch (error) {
      console.error('Failed to fetch quote:', error);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingSpinner />;
  if (!quote) return <ErrorMessage />;

  return (
    <div className="card">
      <h2>{symbol}</h2>
      <p className="price">${quote.price}</p>
      {onRefresh && (
        <button onClick={onRefresh}>Refresh</button>
      )}
    </div>
  );
}
```

**Tools:**

```bash
# Lint
npm run lint

# Format with Prettier (coming soon)
npm run format

# Type check
npm run type-check  # coming soon
```

---

## Testing

### Backend Tests

**Location:** `backend/tests/`

**Naming:**
- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

**Structure:**

```python
import pytest
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestQuotesEndpoint:
    """Integration tests for /api/quotes endpoint."""

    def test_get_quote_returns_200(self, client: TestClient):
        """Test successful quote retrieval."""
        response = client.get("/api/quotes/AAPL")
        assert response.status_code == 200

    def test_get_quote_invalid_symbol_returns_404(self, client: TestClient):
        """Test 404 for invalid symbol."""
        response = client.get("/api/quotes/INVALID123")
        assert response.status_code == 404
```

**Run tests:**

```bash
cd backend

# All tests
pytest

# Specific category
pytest -m unit
pytest -m integration

# Specific file
pytest tests/test_health_endpoints.py -v

# With coverage
pytest --cov=. --cov-report=html
```

### Frontend Tests

**Location:** `frontend/src/**/*.test.tsx`

**Naming:**
- Test files: `*.test.tsx` (next to component)
- Test suites: `describe()`
- Test cases: `it()` or `test()`

**Structure:**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QuoteCard } from './QuoteCard'

describe('QuoteCard', () => {
  it('renders loading state initially', () => {
    render(<QuoteCard symbol="AAPL" />)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('displays quote after loading', async () => {
    render(<QuoteCard symbol="AAPL" />)

    await waitFor(() => {
      expect(screen.getByText('$150.25')).toBeInTheDocument()
    })
  })

  it('calls onRefresh when button clicked', async () => {
    const onRefresh = vi.fn()
    render(<QuoteCard symbol="AAPL" onRefresh={onRefresh} />)

    const button = screen.getByRole('button', { name: /refresh/i })
    fireEvent.click(button)

    expect(onRefresh).toHaveBeenCalledOnce()
  })
})
```

**Run tests:**

```bash
cd frontend

# Watch mode
npm test

# Run once
npm test -- --run

# With coverage
npm run test:coverage

# With UI
npm run test:ui
```

### Coverage Goals

- **Overall:** 80%+
- **Critical paths:** 100% (auth, payment, data fetching)
- **New code:** Must include tests

---

## Commit Guidelines

We follow **Conventional Commits** for clear, semantic commit history.

### Format

```
type(scope): subject

body (optional)

footer (optional)
```

### Types

- `feat` — New feature
- `fix` — Bug fix
- `docs` — Documentation only
- `style` — Code style (formatting, semicolons, etc.)
- `refactor` — Code refactoring (no behavior change)
- `perf` — Performance improvement
- `test` — Adding/updating tests
- `chore` — Maintenance (deps, build, etc.)
- `ci` — CI/CD changes

### Scopes (optional)

- `backend` — Backend changes
- `frontend` — Frontend changes
- `api` — API changes
- `docs` — Documentation
- `deps` — Dependencies

### Examples

**Good commits:**

```bash
git commit -m "feat(api): add GET /api/quotes endpoint"
git commit -m "fix(frontend): resolve chart rendering bug"
git commit -m "docs: update API documentation with rate limits"
git commit -m "test(backend): add tests for cache manager"
git commit -m "chore(deps): update fastapi to 0.110.0"
```

**Bad commits:**

```bash
git commit -m "Update code"          # Too vague
git commit -m "Fixed bug"            # What bug? Where?
git commit -m "WIP"                  # Work in progress shouldn't be committed
git commit -m "asdfasdf"             # Not descriptive
```

### Commit Message Guidelines

**Subject line:**
- Use imperative mood ("add" not "added")
- Don't capitalize first letter
- No period at the end
- Max 50 characters

**Body (optional):**
- Explain *what* and *why*, not *how*
- Wrap at 72 characters
- Separate from subject with blank line

**Footer (optional):**
- Reference issues: `Fixes #123`
- Breaking changes: `BREAKING CHANGE: ...`

**Example with body:**

```
feat(api): add batch quotes endpoint

Allow fetching multiple quotes in a single request to reduce
API calls and improve performance for watchlist updates.

Supports up to 50 symbols per request with comma separation.

Closes #42
```

---

## Pull Request Process

### Before Creating a PR

1. ✅ Tests pass (`pytest` and `npm test`)
2. ✅ Code is formatted and linted
3. ✅ Documentation is updated
4. ✅ Commit messages follow guidelines
5. ✅ Branch is up to date with `main`

### Creating a PR

1. **Push your branch:**

   ```bash
   git push origin feature/your-feature
   ```

2. **Open PR on GitHub**

3. **Fill out PR template:**

   ```markdown
   ## Description
   Brief description of changes.

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   - [ ] Tests pass locally
   - [ ] Added new tests for new features
   - [ ] Manual testing completed

   ## Screenshots (if applicable)
   Add screenshots for UI changes.

   ## Checklist
   - [ ] Code follows style guidelines
   - [ ] Self-review completed
   - [ ] Documentation updated
   - [ ] No new warnings
   ```

4. **Request review**

### PR Review Process

**Reviewers check:**
- Code quality and style
- Test coverage
- Documentation
- Performance implications
- Security concerns

**Feedback:**
- Address all comments
- Make requested changes
- Push updates to same branch
- Re-request review

### After Approval

1. **Squash and merge** (preferred for clean history)
2. **Delete branch** after merge
3. **Close related issues**

---

## Project Structure

### Backend

```
backend/
├── main.py              # FastAPI app entry point
├── config.py            # Settings and env vars
├── models/              # Pydantic models
│   ├── __init__.py
│   ├── base.py
│   └── market.py
├── routers/             # API route handlers
│   ├── __init__.py
│   ├── health.py
│   └── quotes.py        # (future)
├── services/            # Business logic & API integration
│   ├── __init__.py
│   ├── finnhub_service.py  # (future)
│   └── coingecko_service.py  # (future)
├── utils/               # Utilities
│   ├── __init__.py
│   ├── cache.py
│   ├── rate_limiter.py
│   └── logger.py
└── tests/               # Test files
    ├── conftest.py
    ├── test_health_endpoints.py
    └── ...
```

**Guidelines:**
- `models/` — Pydantic models only, no logic
- `routers/` — Thin layer, delegate to services
- `services/` — Business logic, API calls, caching
- `utils/` — Reusable utilities

### Frontend

```
frontend/
├── src/
│   ├── components/      # React components
│   │   ├── Dashboard/
│   │   ├── Watchlist/
│   │   └── Chart/
│   ├── hooks/          # Custom hooks
│   ├── services/       # API client
│   ├── store/          # State management
│   ├── types/          # TypeScript types
│   ├── utils/          # Utilities
│   └── App.tsx
└── tests/              # Test utilities
```

**Guidelines:**
- Components: One component per file
- Hooks: Reusable logic
- Services: API calls only
- Store: Global state

---

## Adding a New Feature

### Backend Endpoint

1. **Define models** (`models/market.py`):

   ```python
   class Quote(BaseModel):
       symbol: str
       price: float
       timestamp: datetime
   ```

2. **Create service** (`services/quotes_service.py`):

   ```python
   async def get_quote(symbol: str) -> Quote:
       # Implement logic
       pass
   ```

3. **Create router** (`routers/quotes.py`):

   ```python
   @router.get("/quotes/{symbol}")
   async def get_quote_endpoint(symbol: str) -> Quote:
       return await get_quote(symbol)
   ```

4. **Register router** (`main.py`):

   ```python
   from routers import quotes_router
   app.include_router(quotes_router)
   ```

5. **Add tests** (`tests/test_quotes.py`):

   ```python
   def test_get_quote_returns_200(client):
       response = client.get("/api/quotes/AAPL")
       assert response.status_code == 200
   ```

### Frontend Component

1. **Define types** (`src/types/quote.ts`):

   ```typescript
   export interface Quote {
     symbol: string;
     price: number;
     timestamp: string;
   }
   ```

2. **Create API client** (`src/services/api.ts`):

   ```typescript
   export async function getQuote(symbol: string): Promise<Quote> {
     const response = await fetch(`${API_URL}/api/quotes/${symbol}`);
     return response.json();
   }
   ```

3. **Create component** (`src/components/QuoteCard/QuoteCard.tsx`):

   ```typescript
   export function QuoteCard({ symbol }: { symbol: string }) {
     // Implementation
   }
   ```

4. **Add tests** (`src/components/QuoteCard/QuoteCard.test.tsx`):

   ```typescript
   describe('QuoteCard', () => {
     it('renders correctly', () => {
       render(<QuoteCard symbol="AAPL" />);
     });
   });
   ```

---

## Getting Help

- **Documentation:** Check README.md, TESTING.md, DEPLOYMENT.md
- **API Docs:** http://localhost:8000/docs
- **Issues:** Search existing issues on GitHub
- **Questions:** Open a discussion or issue

---

## Code of Conduct

Be respectful, professional, and constructive:

- ✅ Provide constructive feedback
- ✅ Accept criticism gracefully
- ✅ Focus on what's best for the project
- ❌ No harassment or discrimination
- ❌ No spam or trolling

---

**Thank you for contributing! 🎉**
