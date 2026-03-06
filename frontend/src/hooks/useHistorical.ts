/**
 * React Query hooks for historical data
 */
import { useQuery } from '@tanstack/react-query';
import { historicalApi } from '../api/client';
import type { HistoricalData, Interval, TimeRange } from '../types';
import { TIME_RANGE_TO_INTERVAL, TIME_RANGE_TO_LIMIT } from '../types';

export const historicalKeys = {
  all: ['historical'] as const,
  forSymbol: (symbol: string, interval: Interval, limit?: number) =>
    [...historicalKeys.all, symbol, interval, limit] as const,
};

/** Fetch historical candles */
export function useHistorical(
  symbol: string | null,
  interval: Interval = '1d',
  limit?: number,
) {
  return useQuery<HistoricalData, Error>({
    queryKey: historicalKeys.forSymbol(symbol ?? '', interval, limit),
    queryFn: () => historicalApi.get(symbol!, interval, limit),
    enabled: !!symbol,
    staleTime: 5 * 60_000, // 5 minutes
    retry: 2,
  });
}

/** Convenience wrapper – derives interval & limit from a TimeRange string */
export function useHistoricalByTimeRange(symbol: string | null, timeRange: TimeRange) {
  const interval = TIME_RANGE_TO_INTERVAL[timeRange];
  const limit = TIME_RANGE_TO_LIMIT[timeRange];
  return useHistorical(symbol, interval, limit);
}
