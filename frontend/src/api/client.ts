/**
 * Market Monitor API Client
 *
 * Axios-based HTTP client with typed methods for all API endpoints.
 */
import axios, { type AxiosInstance, type AxiosError } from 'axios';
import type {
  Quote,
  BatchQuotesResponse,
  HistoricalData,
  Interval,
  ScreenerCriteria,
  ScreenerResponse,
  HealthCheck,
} from '../types';

// ─── Configuration ────────────────────────────────────────────────────────────

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000';

// ─── Error Types ──────────────────────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

function normalizeError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;

  const axErr = err as AxiosError<{
    error?: string;
    message?: string;
    detail?: unknown;
  }>;

  if (axErr.response) {
    const { status, data } = axErr.response;
    return new ApiError(
      status,
      data?.error ?? 'UnknownError',
      data?.message ?? axErr.message,
      data?.detail,
    );
  }

  return new ApiError(0, 'NetworkError', (err as Error).message ?? 'Network error');
}

// ─── Axios Instance ───────────────────────────────────────────────────────────

function createAxios(): AxiosInstance {
  const instance = axios.create({
    baseURL: BASE_URL,
    timeout: 15_000,
    headers: { 'Content-Type': 'application/json' },
  });

  // Response interceptor – normalise errors
  instance.interceptors.response.use(
    (res) => res,
    (err: unknown) => Promise.reject(normalizeError(err)),
  );

  return instance;
}

const http = createAxios();

// ─── API Methods ─────────────────────────────────────────────────────────────

/** Health & diagnostics */
export const healthApi = {
  get: () => http.get<HealthCheck>('/health').then((r) => r.data),
  cache: () =>
    http.get<Record<string, { size: number; maxsize: number; ttl: number }>>('/health/cache').then((r) => r.data),
  rateLimits: () =>
    http
      .get<
        Record<
          string,
          { calls_last_minute: number; limit: number; is_rate_limited: boolean; rate_limit_until: string | null }
        >
      >('/health/rate-limits')
      .then((r) => r.data),
};

/** Quotes */
export const quotesApi = {
  get: (symbol: string, source?: string) =>
    http
      .get<Quote>(`/api/quotes/${encodeURIComponent(symbol)}`, { params: source ? { source } : undefined })
      .then((r) => r.data),

  batch: (symbols: string[]) =>
    http
      .get<BatchQuotesResponse>('/api/quotes/batch', { params: { symbols: symbols.join(',') } })
      .then((r) => r.data),
};

/** Historical data */
export const historicalApi = {
  get: (symbol: string, interval: Interval, limit?: number, from?: string, to?: string) =>
    http
      .get<HistoricalData>(`/api/historical/${encodeURIComponent(symbol)}`, {
        params: { interval, ...(limit !== undefined && { limit }), ...(from && { from }), ...(to && { to }) },
      })
      .then((r) => r.data),
};

/** Screener */
export const screenerApi = {
  screen: (criteria: ScreenerCriteria) =>
    http
      .get<ScreenerResponse>('/api/screener', {
        params: {
          asset_type: criteria.asset_type,
          ...(criteria.min_price !== undefined && { min_price: criteria.min_price }),
          ...(criteria.max_price !== undefined && { max_price: criteria.max_price }),
          ...(criteria.min_volume !== undefined && { min_volume: criteria.min_volume }),
          ...(criteria.min_change_percent !== undefined && { min_change_percent: criteria.min_change_percent }),
          ...(criteria.max_change_percent !== undefined && { max_change_percent: criteria.max_change_percent }),
          ...(criteria.limit !== undefined && { limit: criteria.limit }),
        },
      })
      .then((r) => r.data),
};

// ─── WebSocket factory ────────────────────────────────────────────────────────

export function createQuotesWebSocket(): WebSocket {
  return new WebSocket(`${WS_URL}/ws/quotes`);
}

export { BASE_URL, WS_URL };
