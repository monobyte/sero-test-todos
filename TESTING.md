# Testing Guide

Comprehensive testing guide for Market Monitor backend and frontend.

## Table of Contents

- [Backend Testing](#backend-testing)
  - [Setup](#backend-setup)
  - [Running Tests](#running-backend-tests)
  - [Test Structure](#backend-test-structure)
  - [Writing Tests](#writing-backend-tests)
  - [Coverage](#backend-coverage)
- [Frontend Testing](#frontend-testing)
  - [Setup](#frontend-setup)
  - [Running Tests](#running-frontend-tests)
  - [Test Structure](#frontend-test-structure)
  - [Writing Tests](#writing-frontend-tests)
  - [Coverage](#frontend-coverage)
- [Continuous Integration](#continuous-integration)
- [Best Practices](#best-practices)

---

## Backend Testing

### Backend Setup

```bash
cd backend

# Create virtual environment (if not already done)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies (includes pytest)
pip install -r requirements.txt
```

### Running Backend Tests

#### Run All Tests

```bash
pytest
```

#### Run with Verbose Output

```bash
pytest -v
```

#### Run with Coverage

```bash
# Terminal output
pytest --cov=. --cov-report=term-missing

# HTML report
pytest --cov=. --cov-report=html

# Open HTML report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

#### Run Specific Test Categories

Tests are organized with pytest markers:

```bash
# Unit tests only
pytest -m unit

# Integration tests only
pytest -m integration

# Cache functionality tests
pytest -m cache

# Rate limiting tests
pytest -m rate_limit

# Slow tests (excluded by default)
pytest -m "not slow"
```

#### Run Specific Test Files

```bash
# Health endpoints
pytest tests/test_health_endpoints.py -v

# Cache manager
pytest tests/test_cache_manager.py -v

# Rate limiter
pytest tests/test_rate_limiter.py -v

# Models
pytest tests/test_models.py -v
```

#### Run Specific Test Functions

```bash
# Single test
pytest tests/test_health_endpoints.py::TestHealthEndpoints::test_health_check_returns_200 -v

# Test class
pytest tests/test_cache_manager.py::TestCacheManager -v
```

#### Run Tests Matching Pattern

```bash
# All tests with "cache" in name
pytest -k cache -v

# All tests with "rate" in name
pytest -k rate -v
```

### Backend Test Structure

```
backend/
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # Fixtures and configuration
│   ├── test_health_endpoints.py       # Integration tests
│   ├── test_cache_manager.py          # Cache unit tests
│   ├── test_rate_limiter.py           # Rate limiter unit tests
│   └── test_models.py                 # Pydantic model tests
├── pytest.ini                         # pytest configuration
└── requirements.txt                   # Includes pytest dependencies
```

### Writing Backend Tests

#### Example Integration Test (API Endpoint)

```python
import pytest
from fastapi import status
from fastapi.testclient import TestClient


@pytest.mark.integration
class TestMyEndpoint:
    """Integration tests for /api/my-endpoint"""

    def test_endpoint_returns_200(self, client: TestClient):
        """Test that endpoint returns 200 OK."""
        response = client.get("/api/my-endpoint")
        assert response.status_code == status.HTTP_200_OK

    def test_endpoint_response_structure(self, client: TestClient):
        """Test response has expected structure."""
        response = client.get("/api/my-endpoint")
        data = response.json()
        
        assert "key" in data
        assert isinstance(data["key"], str)
```

#### Example Unit Test (Service Function)

```python
import pytest
from my_service import fetch_data


@pytest.mark.unit
class TestMyService:
    """Unit tests for my_service module."""

    def test_fetch_data_success(self, monkeypatch):
        """Test successful data fetch."""
        # Mock external API call
        def mock_api_call(url):
            return {"data": "mocked"}
        
        monkeypatch.setattr("my_service.api_call", mock_api_call)
        
        result = fetch_data("AAPL")
        assert result["data"] == "mocked"

    def test_fetch_data_error_handling(self, monkeypatch):
        """Test error handling when API fails."""
        def mock_api_call(url):
            raise Exception("API Error")
        
        monkeypatch.setattr("my_service.api_call", mock_api_call)
        
        with pytest.raises(Exception):
            fetch_data("AAPL")
```

#### Using Fixtures

```python
# In tests/conftest.py
@pytest.fixture
def sample_quote_data():
    """Fixture providing sample quote data."""
    return {
        "symbol": "AAPL",
        "price": 150.25,
        "volume": 50000000,
    }


# In test file
def test_process_quote(sample_quote_data):
    """Test quote processing."""
    result = process_quote(sample_quote_data)
    assert result["symbol"] == "AAPL"
```

### Backend Coverage

#### Coverage Goals

- **Overall:** 80%+ coverage
- **Critical paths:** 100% (health checks, caching, rate limiting)
- **Edge cases:** Error handling, fallbacks, validation

#### Viewing Coverage

```bash
# Generate HTML report
pytest --cov=. --cov-report=html

# Open in browser
open htmlcov/index.html
```

Coverage report shows:
- Lines executed vs. total lines
- Branches taken (if/else paths)
- Missing lines (not covered by tests)

#### Exclude from Coverage

Edit `pytest.ini`:

```ini
[coverage:run]
omit = 
    tests/*
    */__pycache__/*
    */venv/*
    test_*.py
```

---

## Frontend Testing

### Frontend Setup

```bash
cd frontend

# Install dependencies (if not already done)
npm install
```

Dependencies include:
- `vitest` — Fast unit test framework
- `@testing-library/react` — React component testing utilities
- `@testing-library/user-event` — Simulate user interactions
- `@testing-library/jest-dom` — Custom matchers (toBeInTheDocument, etc.)
- `jsdom` — DOM environment for Node.js
- `@vitest/ui` — Visual test UI

### Running Frontend Tests

#### Run Tests (Watch Mode)

```bash
npm test
```

This starts Vitest in watch mode:
- Automatically re-runs tests on file changes
- Interactive CLI for filtering tests
- Fast HMR-like experience

#### Run Tests Once

```bash
npm test -- --run
```

#### Run with Coverage

```bash
npm run test:coverage
```

Coverage report:
- Terminal: Summary table
- HTML: `frontend/coverage/index.html`

#### Run with UI

```bash
npm run test:ui
```

Opens browser-based test UI:
- Visual test results
- Code coverage visualization
- Test file explorer
- Re-run tests on demand

#### Run Specific Test Files

```bash
# Single file
npm test -- App.test.tsx

# Pattern matching
npm test -- --grep "component"
```

### Frontend Test Structure

```
frontend/
├── src/
│   ├── App.test.tsx                   # Example component test
│   ├── components/
│   │   ├── Watchlist.test.tsx
│   │   ├── Chart.test.tsx
│   │   └── Dashboard.test.tsx
│   └── test/
│       └── setup.ts                   # Vitest global setup
├── vite.config.ts                     # Vitest configuration
└── package.json                       # Test scripts
```

### Writing Frontend Tests

#### Example Component Test

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import MyComponent from './MyComponent'

describe('MyComponent', () => {
  it('renders without crashing', () => {
    render(<MyComponent />)
    expect(screen.getByText('Hello World')).toBeInTheDocument()
  })

  it('handles button click', () => {
    render(<MyComponent />)
    
    const button = screen.getByRole('button', { name: /click me/i })
    fireEvent.click(button)
    
    expect(screen.getByText('Clicked!')).toBeInTheDocument()
  })
})
```

#### Testing User Interactions

```typescript
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Form from './Form'

it('submits form with user input', async () => {
  const user = userEvent.setup()
  render(<Form />)
  
  // Type in input
  const input = screen.getByLabelText('Symbol')
  await user.type(input, 'AAPL')
  
  // Click submit
  const submit = screen.getByRole('button', { name: /submit/i })
  await user.click(submit)
  
  // Verify result
  expect(screen.getByText('Submitted: AAPL')).toBeInTheDocument()
})
```

#### Testing Async Components

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import AsyncComponent from './AsyncComponent'

it('loads data asynchronously', async () => {
  render(<AsyncComponent />)
  
  // Initially shows loading
  expect(screen.getByText('Loading...')).toBeInTheDocument()
  
  // Wait for data to load
  await waitFor(() => {
    expect(screen.getByText('Data loaded')).toBeInTheDocument()
  })
})
```

#### Mocking API Calls

```typescript
import { vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import DataComponent from './DataComponent'

// Mock fetch
global.fetch = vi.fn(() =>
  Promise.resolve({
    json: () => Promise.resolve({ symbol: 'AAPL', price: 150.25 }),
  })
) as any

it('fetches and displays data', async () => {
  render(<DataComponent symbol="AAPL" />)
  
  await waitFor(() => {
    expect(screen.getByText('150.25')).toBeInTheDocument()
  })
  
  expect(fetch).toHaveBeenCalledWith('/api/quotes/AAPL')
})
```

### Frontend Coverage

#### Coverage Goals

- **Overall:** 70%+ coverage
- **Critical components:** 90%+ (Watchlist, Chart, Dashboard)
- **Utility functions:** 100%

#### Viewing Coverage

```bash
npm run test:coverage

# Open HTML report
open coverage/index.html
```

#### Exclude from Coverage

Edit `vite.config.ts`:

```typescript
export default defineConfig({
  test: {
    coverage: {
      exclude: [
        'node_modules/',
        'src/test/',
        '**/*.config.ts',
        '**/*.config.js',
        'src/main.tsx',  // Entry point
      ],
    },
  },
})
```

---

## Continuous Integration

### GitHub Actions Workflow

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  backend:
    name: Backend Tests
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd backend
          pip install -r requirements.txt
      
      - name: Run tests with coverage
        run: |
          cd backend
          pytest --cov=. --cov-report=xml --cov-report=term
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./backend/coverage.xml
          flags: backend

  frontend:
    name: Frontend Tests
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: frontend/package-lock.json
      
      - name: Install dependencies
        run: |
          cd frontend
          npm ci
      
      - name: Run tests with coverage
        run: |
          cd frontend
          npm run test:coverage
      
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./frontend/coverage/coverage-final.json
          flags: frontend
```

### Pre-commit Hook

Create `.git/hooks/pre-commit`:

```bash
#!/bin/bash

echo "Running backend tests..."
cd backend
pytest --cov=. --cov-fail-under=80
BACKEND_EXIT=$?

echo "Running frontend tests..."
cd ../frontend
npm test -- --run
FRONTEND_EXIT=$?

if [ $BACKEND_EXIT -ne 0 ] || [ $FRONTEND_EXIT -ne 0 ]; then
    echo "Tests failed! Commit aborted."
    exit 1
fi

echo "All tests passed!"
exit 0
```

Make executable:

```bash
chmod +x .git/hooks/pre-commit
```

---

## Best Practices

### General Testing Principles

1. **Test behavior, not implementation**
   - ❌ Don't test internal state
   - ✅ Test public API and user-visible behavior

2. **Write descriptive test names**
   - ❌ `test_1()`, `test_cache()`
   - ✅ `test_cache_returns_none_for_missing_key()`

3. **One assertion per test** (when possible)
   - Makes failures easier to debug
   - Each test has a single, clear purpose

4. **Use fixtures for setup**
   - Avoid repetitive setup code
   - Keep tests focused on assertions

5. **Mock external dependencies**
   - Don't call real APIs in tests
   - Use monkeypatch or mock libraries

### Backend-Specific

1. **Test error cases**
   ```python
   def test_endpoint_handles_missing_parameter(client):
       response = client.get("/api/quotes")  # Missing symbol
       assert response.status_code == 422
   ```

2. **Test validation**
   ```python
   def test_model_rejects_invalid_data():
       with pytest.raises(ValidationError):
           MyModel(invalid_field="value")
   ```

3. **Test fallback logic**
   ```python
   def test_uses_fallback_when_primary_fails(monkeypatch):
       monkeypatch.setattr("service.primary_api", mock_failure)
       result = service.fetch_data()
       assert result.source == "fallback"
   ```

### Frontend-Specific

1. **Test accessibility**
   ```typescript
   it('has accessible button', () => {
     render(<MyComponent />)
     const button = screen.getByRole('button', { name: /submit/i })
     expect(button).toBeInTheDocument()
   })
   ```

2. **Test user flows**
   ```typescript
   it('completes checkout flow', async () => {
     const user = userEvent.setup()
     render(<Checkout />)
     
     await user.type(screen.getByLabelText('Email'), 'test@example.com')
     await user.click(screen.getByRole('button', { name: /continue/i }))
     
     expect(screen.getByText('Order confirmed')).toBeInTheDocument()
   })
   ```

3. **Test edge cases**
   - Empty states
   - Loading states
   - Error states

### What NOT to Test

- **Third-party libraries** (trust they're tested)
- **Framework internals** (React, FastAPI, etc.)
- **Generated code** (migrations, OpenAPI schemas)
- **Trivial getters/setters**

### Test Maintenance

- **Delete obsolete tests** when refactoring
- **Update tests** when requirements change
- **Fix flaky tests** immediately (don't ignore)
- **Review coverage** after each feature

---

## Troubleshooting

### Backend Issues

**Issue:** `ModuleNotFoundError: No module named 'pytest'`

**Solution:**
```bash
pip install -r requirements.txt
```

**Issue:** Tests pass locally but fail in CI

**Solution:**
- Check Python version (CI may use different version)
- Ensure all dependencies in `requirements.txt`
- Check for hardcoded paths (use `pathlib`)

### Frontend Issues

**Issue:** `ReferenceError: document is not defined`

**Solution:**
- Ensure `jsdom` is installed
- Check `vite.config.ts` has `environment: 'jsdom'`

**Issue:** Tests timeout waiting for elements

**Solution:**
- Use `waitFor()` for async operations
- Increase timeout: `waitFor(() => {...}, { timeout: 5000 })`
- Check if component actually renders the element

---

## Resources

### Backend
- [pytest Documentation](https://docs.pytest.org/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)

### Frontend
- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/react)
- [Testing Library Cheatsheet](https://testing-library.com/docs/react-testing-library/cheatsheet)

---

**Happy Testing! 🧪**
