# Market Monitor Frontend

Modern React + TypeScript frontend for the Market Monitor personal finance and trading research application.

## Features

- 📊 Real-time price monitoring dashboard
- 📈 Interactive candlestick charts
- 🔍 Stock and crypto screening
- 🎯 Trading idea generation
- 📱 Responsive design with TailwindCSS
- ⚡ Fast development with Vite + HMR
- 🔒 Type-safe with TypeScript strict mode

## Tech Stack

- **React 19** — UI framework
- **TypeScript 5.9** — Type safety
- **Vite 7** — Build tool and dev server
- **TailwindCSS 4** — Utility-first styling
- **Zustand** — State management (coming soon)
- **Recharts** — Charts and visualizations (coming soon)
- **React Router** — Navigation (coming soon)

## Quick Start

### Prerequisites

- Node.js 18+ and npm

### Installation

```bash
# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend will be available at http://localhost:3000 (or the port shown in terminal)

### Build for Production

```bash
# Build optimized production bundle
npm run build

# Preview production build
npm run preview
```

Build output: `dist/`

## Development

### Project Structure

```
frontend/
├── public/                    # Static assets
├── src/
│   ├── components/           # React components (coming soon)
│   │   ├── Dashboard/
│   │   ├── Watchlist/
│   │   ├── Chart/
│   │   └── Screener/
│   ├── hooks/               # Custom React hooks (coming soon)
│   ├── services/            # API client (coming soon)
│   ├── store/               # Zustand state (coming soon)
│   ├── types/               # TypeScript types (coming soon)
│   ├── utils/               # Utility functions (coming soon)
│   ├── App.tsx              # Root component
│   ├── main.tsx             # Entry point
│   └── test/                # Test utilities
│       └── setup.ts         # Vitest setup
├── index.html               # HTML template
├── vite.config.ts           # Vite configuration
├── tsconfig.json            # TypeScript config
├── tailwind.config.js       # Tailwind config (coming soon)
└── package.json             # Dependencies and scripts
```

### Available Scripts

```bash
# Development
npm run dev              # Start dev server with HMR

# Production
npm run build            # Build for production
npm run preview          # Preview production build

# Code Quality
npm run lint             # Lint with ESLint

# Testing
npm test                 # Run tests (watch mode)
npm run test:ui          # Run tests with UI
npm run test:coverage    # Run tests with coverage
```

### Code Style

This project uses:
- **ESLint** for linting
- **TypeScript strict mode** for type safety
- **Prettier** (coming soon) for formatting

### Environment Variables

Create `.env.local` for local development:

```bash
# Backend API URL
VITE_API_URL=http://localhost:8000

# WebSocket URL
VITE_WS_URL=ws://localhost:8000
```

Access in code:

```typescript
const API_URL = import.meta.env.VITE_API_URL;
```

## Testing

### Running Tests

```bash
# Watch mode (default)
npm test

# Run once
npm test -- --run

# With coverage
npm run test:coverage

# With UI
npm run test:ui
```

### Writing Tests

Example component test:

```typescript
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import MyComponent from './MyComponent'

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />)
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })
})
```

See [TESTING.md](../TESTING.md) for comprehensive testing guide.

## API Integration

### Fetching Data

Example API client (coming soon):

```typescript
// src/services/api.ts
const API_URL = import.meta.env.VITE_API_URL;

export async function getQuote(symbol: string) {
  const response = await fetch(`${API_URL}/api/quotes/${symbol}`);
  if (!response.ok) throw new Error('Failed to fetch quote');
  return response.json();
}
```

### Using in Components

```typescript
import { useEffect, useState } from 'react';
import { getQuote } from './services/api';

function QuoteCard({ symbol }: { symbol: string }) {
  const [quote, setQuote] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getQuote(symbol)
      .then(setQuote)
      .finally(() => setLoading(false));
  }, [symbol]);

  if (loading) return <div>Loading...</div>;
  return <div>{quote.price}</div>;
}
```

## WebSocket Integration (Coming Soon)

Real-time price updates:

```typescript
import { useEffect } from 'react';

const WS_URL = import.meta.env.VITE_WS_URL;

function usePriceUpdates(symbols: string[]) {
  useEffect(() => {
    const ws = new WebSocket(`${WS_URL}/ws/quotes`);

    ws.onopen = () => {
      ws.send(JSON.stringify({
        action: 'subscribe',
        symbols
      }));
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      console.log('Price update:', data);
    };

    return () => ws.close();
  }, [symbols]);
}
```

## State Management (Coming Soon)

Using Zustand for global state:

```typescript
// src/store/useStore.ts
import create from 'zustand';

interface StoreState {
  watchlist: string[];
  addToWatchlist: (symbol: string) => void;
  removeFromWatchlist: (symbol: string) => void;
}

export const useStore = create<StoreState>((set) => ({
  watchlist: [],
  addToWatchlist: (symbol) =>
    set((state) => ({ watchlist: [...state.watchlist, symbol] })),
  removeFromWatchlist: (symbol) =>
    set((state) => ({
      watchlist: state.watchlist.filter((s) => s !== symbol),
    })),
}));
```

## Deployment

### Build

```bash
npm run build
```

Output: `dist/` directory

### Deploy to Vercel

```bash
# Install Vercel CLI
npm install -g vercel

# Deploy
vercel

# Production
vercel --prod
```

### Deploy to Netlify

```bash
# Install Netlify CLI
npm install -g netlify-cli

# Deploy
netlify deploy

# Production
netlify deploy --prod
```

### Deploy to Static Hosting

Upload `dist/` to any static hosting:

- GitHub Pages
- Cloudflare Pages
- AWS S3 + CloudFront
- Firebase Hosting

Configure SPA fallback:
- All routes should serve `index.html`

## Browser Support

- Chrome/Edge (latest)
- Firefox (latest)
- Safari (latest)

## Performance

- Code splitting with React.lazy (coming soon)
- Image optimization
- Service worker for caching (coming soon)
- Lighthouse score target: 90+

## Accessibility

- Semantic HTML
- ARIA labels
- Keyboard navigation
- Screen reader support

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development workflow.

## License

Personal use only. See root [README.md](../README.md) for details.

---

**Built with ⚡ Vite + ⚛️ React + 📘 TypeScript**
