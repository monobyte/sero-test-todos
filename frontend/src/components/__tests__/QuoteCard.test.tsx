import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { QuoteCard, AddSymbolCard } from '../QuoteCard';
import userEvent from '@testing-library/user-event';
import type { Quote } from '../../types';

// Hoist mock functions so they're available inside vi.mock factory
const { mockGetFn } = vi.hoisted(() => ({ mockGetFn: vi.fn() }));

// Mock icons
vi.mock('lucide-react', () => ({
  TrendingUp: () => <svg data-testid="icon-up" />,
  TrendingDown: () => <svg data-testid="icon-down" />,
  Minus: () => <svg data-testid="icon-minus" />,
  Plus: () => <svg data-testid="icon-plus" />,
  X: () => <svg data-testid="icon-x" />,
  Star: () => <svg data-testid="icon-star" />,
}));

vi.mock('../../api/client', () => ({
  quotesApi: { get: mockGetFn, batch: vi.fn() },
  historicalApi: { get: vi.fn() },
  screenerApi: { screen: vi.fn() },
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

const mockQuote: Quote = {
  symbol: 'AAPL',
  price: 175.23,
  change: 3.45,
  change_percent: 2.01,
  volume: 52_000_000,
  high: 176.10,
  low: 171.80,
  timestamp: '2026-03-06T14:00:00Z',
  source: 'finnhub',
  cached: false,
  asset_type: 'stock',
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe('QuoteCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading state initially', () => {
    // Never resolves – stays in loading
    mockGetFn.mockReturnValue(new Promise(() => {}));
    render(<QuoteCard symbol="AAPL" />, { wrapper: makeWrapper() });
    expect(screen.getByRole('status')).toBeInTheDocument(); // Spinner
  });

  it('renders quote data when loaded', async () => {
    mockGetFn.mockResolvedValue(mockQuote);
    render(<QuoteCard symbol="AAPL" />, { wrapper: makeWrapper() });

    expect(await screen.findByText('AAPL')).toBeInTheDocument();
    expect(await screen.findByText(/175\.23/)).toBeInTheDocument();
  });

  it('shows error state on failed fetch', async () => {
    mockGetFn.mockRejectedValue(new Error('Network error'));
    render(<QuoteCard symbol="AAPL" />, { wrapper: makeWrapper() });

    // Wait for error element to appear (React Query v5 + retry:false)
    expect(await screen.findByTestId('quote-error', {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('calls onClick when card is clicked', async () => {
    const user = userEvent.setup();
    mockGetFn.mockReturnValue(new Promise(() => {}));
    const onClick = vi.fn();

    render(<QuoteCard symbol="AAPL" onClick={onClick} />, { wrapper: makeWrapper() });
    // Click the outer card specifically
    await user.click(screen.getByTestId('quote-card'));
    expect(onClick).toHaveBeenCalled();
  });
});

describe('AddSymbolCard', () => {
  it('calls onAdd with the uppercased typed symbol', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();

    render(<AddSymbolCard onAdd={onAdd} />);

    const input = screen.getByPlaceholderText(/add symbol/i);
    await user.type(input, 'tsla');
    await user.keyboard('{Enter}');

    expect(onAdd).toHaveBeenCalledWith('TSLA');
  });

  it('does not call onAdd for empty input', async () => {
    const user = userEvent.setup();
    const onAdd = vi.fn();

    render(<AddSymbolCard onAdd={onAdd} />);
    await user.keyboard('{Enter}');

    expect(onAdd).not.toHaveBeenCalled();
  });
});
