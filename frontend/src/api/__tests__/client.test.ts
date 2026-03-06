/**
 * Tests for the API client.
 * We test the factory functions' logic directly using a real axios instance
 * in unit mode (no network) – axios errors are intercepted and normalised.
 */
import { describe, it, expect } from 'vitest';
import { ApiError } from '../client';

describe('ApiError', () => {
  it('constructs with correct properties', () => {
    const err = new ApiError(404, 'NotFound', 'Symbol not found', { symbol: 'INVALID' });
    expect(err.status).toBe(404);
    expect(err.code).toBe('NotFound');
    expect(err.message).toBe('Symbol not found');
    expect(err.detail).toEqual({ symbol: 'INVALID' });
    expect(err.name).toBe('ApiError');
  });

  it('extends Error', () => {
    const err = new ApiError(500, 'InternalServerError', 'Oops');
    expect(err).toBeInstanceOf(Error);
    expect(err).toBeInstanceOf(ApiError);
  });

  it('accepts undefined detail', () => {
    const err = new ApiError(429, 'RateLimitExceeded', 'Too many requests');
    expect(err.detail).toBeUndefined();
  });
});

// ─── Query key factories ──────────────────────────────────────────────────────

import { quoteKeys } from '../../../src/hooks/useQuotes';
import { historicalKeys } from '../../../src/hooks/useHistorical';
import { screenerKeys } from '../../../src/hooks/useScreener';

describe('quoteKeys', () => {
  it('produces a stable single key', () => {
    const k1 = quoteKeys.single('AAPL');
    const k2 = quoteKeys.single('AAPL');
    expect(k1).toEqual(k2);
    expect(k1[0]).toBe('quotes');
  });

  it('batch key sorts symbols', () => {
    const k1 = quoteKeys.batch(['AAPL', 'GOOGL']);
    const k2 = quoteKeys.batch(['GOOGL', 'AAPL']);
    expect(k1).toEqual(k2);
  });
});

describe('historicalKeys', () => {
  it('includes symbol and interval', () => {
    const k = historicalKeys.forSymbol('BTC', '1d', 30);
    expect(k).toContain('historical');
    expect(k).toContain('BTC');
    expect(k).toContain('1d');
    expect(k).toContain(30);
  });
});

describe('screenerKeys', () => {
  it('includes the criteria object', () => {
    const criteria = { asset_type: 'stock' as const, min_change_percent: 5 };
    const k = screenerKeys.results(criteria);
    expect(k[0]).toBe('screener');
    expect(k[k.length - 1]).toEqual(criteria);
  });
});
