/**
 * React Query hooks for quote data
 */
import { useQuery, useQueries } from '@tanstack/react-query';
import { quotesApi } from '../api/client';
import type { Quote } from '../types';

// Query keys factory
export const quoteKeys = {
  all: ['quotes'] as const,
  single: (symbol: string, source?: string) =>
    [...quoteKeys.all, symbol, source] as const,
  batch: (symbols: string[]) =>
    [...quoteKeys.all, 'batch', symbols.slice().sort().join(',')] as const,
};

/** Fetch a single quote, refreshes every 30s */
export function useQuote(symbol: string | null, source?: string) {
  return useQuery<Quote, Error>({
    queryKey: quoteKeys.single(symbol ?? '', source),
    queryFn: () => quotesApi.get(symbol!, source),
    enabled: !!symbol,
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: 2,
  });
}

/** Fetch multiple quotes in parallel */
export function useMultipleQuotes(symbols: string[]) {
  return useQueries({
    queries: symbols.map((sym) => ({
      queryKey: quoteKeys.single(sym),
      queryFn: () => quotesApi.get(sym),
      staleTime: 30_000,
      refetchInterval: 30_000,
      retry: 2,
    })),
  });
}

/** Fetch a batch of quotes in one request */
export function useBatchQuotes(symbols: string[], enabled = true) {
  return useQuery({
    queryKey: quoteKeys.batch(symbols),
    queryFn: () => quotesApi.batch(symbols),
    enabled: enabled && symbols.length > 0,
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: 2,
  });
}
