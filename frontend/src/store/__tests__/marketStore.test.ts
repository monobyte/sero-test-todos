import { describe, it, expect, beforeEach } from 'vitest';
import { useMarketStore } from '../marketStore';

// Reset store state between tests
beforeEach(() => {
  useMarketStore.setState({
    watchlist: [],
    liveQuotes: {},
    selectedSymbol: null,
    activeTab: 'dashboard',
    selectedTimeRange: '1M',
    wsConnected: false,
  });
});

describe('marketStore – watchlist', () => {
  it('adds a symbol to the watchlist', () => {
    const { addToWatchlist, watchlist } = useMarketStore.getState();
    expect(watchlist).toHaveLength(0);

    addToWatchlist('AAPL', 'stock');

    expect(useMarketStore.getState().watchlist).toHaveLength(1);
    expect(useMarketStore.getState().watchlist[0]?.symbol).toBe('AAPL');
  });

  it('does not add duplicate symbols', () => {
    const { addToWatchlist } = useMarketStore.getState();
    addToWatchlist('AAPL', 'stock');
    addToWatchlist('AAPL', 'stock');

    expect(useMarketStore.getState().watchlist).toHaveLength(1);
  });

  it('removes a symbol from the watchlist', () => {
    const store = useMarketStore.getState();
    store.addToWatchlist('AAPL', 'stock');
    store.addToWatchlist('GOOGL', 'stock');

    useMarketStore.getState().removeFromWatchlist('AAPL');

    const { watchlist } = useMarketStore.getState();
    expect(watchlist).toHaveLength(1);
    expect(watchlist[0]?.symbol).toBe('GOOGL');
  });

  it('isInWatchlist returns true for watched symbol', () => {
    useMarketStore.getState().addToWatchlist('BTC', 'crypto');
    expect(useMarketStore.getState().isInWatchlist('BTC')).toBe(true);
  });

  it('isInWatchlist returns false for unwatched symbol', () => {
    expect(useMarketStore.getState().isInWatchlist('ETH')).toBe(false);
  });
});

describe('marketStore – liveQuotes', () => {
  it('updates a live quote', () => {
    useMarketStore.getState().updateLiveQuote('AAPL', { price: 180.5, change: 2.5, change_percent: 1.4 });

    const { liveQuotes } = useMarketStore.getState();
    expect(liveQuotes['AAPL']?.price).toBe(180.5);
  });

  it('merges partial updates', () => {
    useMarketStore.getState().updateLiveQuote('AAPL', { price: 180 });
    useMarketStore.getState().updateLiveQuote('AAPL', { change: 1.5 });

    const q = useMarketStore.getState().liveQuotes['AAPL'];
    expect(q?.price).toBe(180);
    expect(q?.change).toBe(1.5);
  });

  it('clears all live quotes', () => {
    useMarketStore.getState().updateLiveQuote('AAPL', { price: 180 });
    useMarketStore.getState().clearLiveQuotes();

    expect(useMarketStore.getState().liveQuotes).toEqual({});
  });
});

describe('marketStore – UI state', () => {
  it('sets selected symbol', () => {
    useMarketStore.getState().setSelectedSymbol('TSLA');
    expect(useMarketStore.getState().selectedSymbol).toBe('TSLA');
  });

  it('sets active tab', () => {
    useMarketStore.getState().setActiveTab('screener');
    expect(useMarketStore.getState().activeTab).toBe('screener');
  });

  it('sets time range', () => {
    useMarketStore.getState().setSelectedTimeRange('1Y');
    expect(useMarketStore.getState().selectedTimeRange).toBe('1Y');
  });

  it('tracks WebSocket connection status', () => {
    useMarketStore.getState().setWsConnected(true);
    expect(useMarketStore.getState().wsConnected).toBe(true);

    useMarketStore.getState().setWsConnected(false);
    expect(useMarketStore.getState().wsConnected).toBe(false);
  });
});
