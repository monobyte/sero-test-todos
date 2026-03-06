/**
 * TypeScript types for Market Monitor API
 */

// ─── Quote ────────────────────────────────────────────────────────────────────

export interface Quote {
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  market_cap?: number;
  high?: number;
  low?: number;
  open?: number;
  timestamp: string;
  source: string;
  cached: boolean;
  asset_type?: 'stock' | 'crypto';
}

export interface BatchQuotesResponse {
  quotes: Quote[];
  count: number;
  timestamp: string;
}

// ─── Historical / Candles ─────────────────────────────────────────────────────

export type Interval = '1m' | '5m' | '15m' | '1h' | '4h' | '1d' | '1w' | '1M';

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface HistoricalData {
  symbol: string;
  interval: Interval;
  candles: Candle[];
  count: number;
  source: string;
}

// ─── Screener ─────────────────────────────────────────────────────────────────

export type AssetType = 'stock' | 'crypto';

export interface ScreenerCriteria {
  asset_type: AssetType;
  min_price?: number;
  max_price?: number;
  min_volume?: number;
  min_change_percent?: number;
  max_change_percent?: number;
  limit?: number;
}

export interface ScreenerResult {
  symbol: string;
  price: number;
  change_percent: number;
  volume: number;
  market_cap?: number;
}

export interface ScreenerResponse {
  results: ScreenerResult[];
  count: number;
  criteria: Partial<ScreenerCriteria>;
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

export interface WsQuoteMessage {
  type: 'quote';
  symbol: string;
  price: number;
  change: number;
  change_percent: number;
  volume?: number;
  timestamp: string;
}

export interface WsErrorMessage {
  type: 'error';
  message: string;
  symbol?: string;
}

export interface WsPingMessage {
  type: 'ping';
}

export type WsMessage = WsQuoteMessage | WsErrorMessage | WsPingMessage;

export interface WsSubscribeAction {
  action: 'subscribe' | 'unsubscribe';
  symbols: string[];
}

// ─── Health ───────────────────────────────────────────────────────────────────

export interface HealthCheck {
  status: string;
  timestamp: string;
  version: string;
  environment: string;
  services: Record<string, boolean>;
}

// ─── Watchlist ────────────────────────────────────────────────────────────────

export interface WatchlistItem {
  symbol: string;
  addedAt: string;
  assetType?: AssetType;
}

// ─── UI State ─────────────────────────────────────────────────────────────────

export type TimeRange = '1D' | '1W' | '1M' | '3M' | '6M' | '1Y';

export const TIME_RANGE_TO_INTERVAL: Record<TimeRange, Interval> = {
  '1D': '5m',
  '1W': '1h',
  '1M': '1d',
  '3M': '1d',
  '6M': '1d',
  '1Y': '1w',
};

export const TIME_RANGE_TO_LIMIT: Record<TimeRange, number> = {
  '1D': 78,
  '1W': 168,
  '1M': 30,
  '3M': 90,
  '6M': 180,
  '1Y': 52,
};
