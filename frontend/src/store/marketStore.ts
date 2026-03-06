/**
 * Zustand store for Market Monitor state
 *
 * Manages:
 * - Watchlist (persisted to localStorage)
 * - Live quote updates (from WebSocket)
 * - UI state (selected symbol, selected tab, time range)
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Quote, WatchlistItem, TimeRange, AssetType } from '../types';

// ─── Live Quotes slice ────────────────────────────────────────────────────────

interface LiveQuotesSlice {
  /** Map of symbol → latest quote update from WS */
  liveQuotes: Record<string, Partial<Quote>>;
  updateLiveQuote: (symbol: string, update: Partial<Quote>) => void;
  clearLiveQuotes: () => void;
}

// ─── Watchlist slice ──────────────────────────────────────────────────────────

interface WatchlistSlice {
  watchlist: WatchlistItem[];
  addToWatchlist: (symbol: string, assetType?: AssetType) => void;
  removeFromWatchlist: (symbol: string) => void;
  isInWatchlist: (symbol: string) => boolean;
}

// ─── UI State slice ───────────────────────────────────────────────────────────

interface UiSlice {
  selectedSymbol: string | null;
  setSelectedSymbol: (symbol: string | null) => void;

  activeTab: 'dashboard' | 'screener' | 'watchlist';
  setActiveTab: (tab: UiSlice['activeTab']) => void;

  selectedTimeRange: TimeRange;
  setSelectedTimeRange: (range: TimeRange) => void;

  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;
}

// ─── Combined Store ───────────────────────────────────────────────────────────

type MarketStore = LiveQuotesSlice & WatchlistSlice & UiSlice;

export const useMarketStore = create<MarketStore>()(
  persist(
    (set, get) => ({
      // ── Live quotes ──────────────────────────────────────────────────────────
      liveQuotes: {},

      updateLiveQuote: (symbol, update) =>
        set((state) => ({
          liveQuotes: {
            ...state.liveQuotes,
            [symbol]: { ...(state.liveQuotes[symbol] ?? {}), ...update },
          },
        })),

      clearLiveQuotes: () => set({ liveQuotes: {} }),

      // ── Watchlist ─────────────────────────────────────────────────────────
      watchlist: [
        // Seed with some defaults so the UI isn't empty on first load
        { symbol: 'AAPL', addedAt: new Date().toISOString(), assetType: 'stock' },
        { symbol: 'GOOGL', addedAt: new Date().toISOString(), assetType: 'stock' },
        { symbol: 'BTC', addedAt: new Date().toISOString(), assetType: 'crypto' },
      ],

      addToWatchlist: (symbol, assetType) => {
        const upper = symbol.toUpperCase();
        if (get().watchlist.some((w) => w.symbol.toUpperCase() === upper)) return;
        set((state) => ({
          watchlist: [
            ...state.watchlist,
            { symbol, addedAt: new Date().toISOString(), assetType },
          ],
        }));
      },

      removeFromWatchlist: (symbol) =>
        set((state) => ({
          watchlist: state.watchlist.filter(
            (w) => w.symbol.toLowerCase() !== symbol.toLowerCase(),
          ),
        })),

      isInWatchlist: (symbol) =>
        get().watchlist.some((w) => w.symbol.toLowerCase() === symbol.toLowerCase()),

      // ── UI State ─────────────────────────────────────────────────────────
      selectedSymbol: 'AAPL',
      setSelectedSymbol: (symbol) => set({ selectedSymbol: symbol }),

      activeTab: 'dashboard',
      setActiveTab: (tab) => set({ activeTab: tab }),

      selectedTimeRange: '1M',
      setSelectedTimeRange: (range) => set({ selectedTimeRange: range }),

      wsConnected: false,
      setWsConnected: (connected) => set({ wsConnected: connected }),
    }),
    {
      name: 'market-monitor-store',
      version: 1,
      // Only persist watchlist and UI prefs — not live quotes or WS state
      partialize: (state) => ({
        watchlist: state.watchlist,
        selectedSymbol: state.selectedSymbol,
        selectedTimeRange: state.selectedTimeRange,
        activeTab: state.activeTab,
      }),
      migrate: (persisted: unknown, version: number) => {
        const state = persisted as Record<string, unknown>;
        if (version === 0) {
          // v0→v1: rename "bitcoin" watchlist entry to "BTC"
          const watchlist = state.watchlist as WatchlistItem[] | undefined;
          if (watchlist) {
            state.watchlist = watchlist.map((w) =>
              w.symbol.toLowerCase() === 'bitcoin'
                ? { ...w, symbol: 'BTC', assetType: 'crypto' as AssetType }
                : w,
            );
          }
        }
        return state;
      },
    },
  ),
);
