/**
 * React Query hooks for the screener
 */
import { useQuery } from '@tanstack/react-query';
import { screenerApi } from '../api/client';
import type { ScreenerCriteria, ScreenerResponse } from '../types';

export const screenerKeys = {
  all: ['screener'] as const,
  results: (criteria: ScreenerCriteria) =>
    [...screenerKeys.all, 'results', criteria] as const,
};

/** Run a screener query. Only fetches when `enabled` is true. */
export function useScreener(criteria: ScreenerCriteria, enabled = false) {
  return useQuery<ScreenerResponse, Error>({
    queryKey: screenerKeys.results(criteria),
    queryFn: () => screenerApi.screen(criteria),
    enabled,
    staleTime: 2 * 60_000, // 2 minutes
    retry: 1,
  });
}
