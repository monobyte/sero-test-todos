/**
 * Tests for App component
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from './App';

// ── Mock lucide-react (SVG rendering in jsdom is noisy) ──────────────────────
vi.mock('lucide-react', () => ({
  BarChart2: () => <svg data-testid="icon-barchart" />,
  Search: () => <svg data-testid="icon-search" />,
  Star: () => <svg data-testid="icon-star" />,
  Activity: () => <svg data-testid="icon-activity" />,
  TrendingUp: () => <svg data-testid="icon-up" />,
  TrendingDown: () => <svg data-testid="icon-down" />,
  Minus: () => <svg data-testid="icon-minus" />,
  Plus: () => <svg data-testid="icon-plus" />,
  X: () => <svg data-testid="icon-x" />,
  Wifi: () => <svg data-testid="icon-wifi" />,
  WifiOff: () => <svg data-testid="icon-wifi-off" />,
  ChevronUp: () => <svg data-testid="icon-chevron-up" />,
  ChevronDown: () => <svg data-testid="icon-chevron-down" />,
}));

// ── Mock API calls – don't hit real network in unit tests ────────────────────
vi.mock('./api/client', () => ({
  quotesApi: { get: vi.fn().mockResolvedValue(null), batch: vi.fn().mockResolvedValue({ quotes: [], count: 0, timestamp: '' }) },
  historicalApi: { get: vi.fn().mockResolvedValue(null) },
  screenerApi: { screen: vi.fn().mockResolvedValue({ results: [], count: 0, criteria: {} }) },
  createQuotesWebSocket: vi.fn(() => ({
    send: vi.fn(),
    close: vi.fn(),
    readyState: 1,
    onopen: null,
    onmessage: null,
    onclose: null,
    onerror: null,
  })),
  BASE_URL: 'http://localhost:8000',
  WS_URL: 'ws://localhost:8000',
}));

// ── Mock Recharts (canvas not available in jsdom) ────────────────────────────
vi.mock('recharts', () => ({
  AreaChart: ({ children }: { children?: React.ReactNode }) => <div data-testid="area-chart">{children}</div>,
  Area: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children?: React.ReactNode }) => <div>{children}</div>,
  BarChart: ({ children }: { children?: React.ReactNode }) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => null,
  ComposedChart: ({ children }: { children?: React.ReactNode }) => <div data-testid="composed-chart">{children}</div>,
}));

// ─────────────────────────────────────────────────────────────────────────────

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the app header with brand name', () => {
    render(<App />);
    expect(screen.getByText('Market Monitor')).toBeInTheDocument();
  });

  it('shows navigation tabs', () => {
    render(<App />);
    // Use nav element to scope the query and avoid collisions with icon buttons
    const nav = screen.getByRole('navigation');
    expect(nav).toBeInTheDocument();
    expect(nav.textContent).toContain('Dashboard');
    expect(nav.textContent).toContain('Screener');
    expect(nav.textContent).toContain('Watchlist');
  });

  it('shows Dashboard tab by default', () => {
    render(<App />);
    // The Dashboard heading is rendered inside the main content
    const headings = screen.getAllByText('Dashboard');
    expect(headings.length).toBeGreaterThan(0);
  });

  it('switches to Screener tab when clicked', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: /screener/i }));
    expect(screen.getByText('Market Screener')).toBeInTheDocument();
  });

  it('switches to Watchlist tab when clicked', async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole('button', { name: /watchlist/i }));
    // Watchlist page shows an h2 heading
    const headings = screen.getAllByText('Watchlist');
    expect(headings.length).toBeGreaterThan(0);
  });
});
