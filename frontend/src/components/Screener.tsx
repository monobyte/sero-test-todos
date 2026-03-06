/**
 * Screener – filter panel + results table for stock/crypto screening.
 */
import { useState } from 'react';
import { Search, ChevronUp, ChevronDown, Minus } from 'lucide-react';
import { Spinner } from './ui/Spinner';
import { useScreener } from '../hooks/useScreener';
import { useMarketStore } from '../store/marketStore';
import type { ScreenerCriteria, AssetType, ScreenerResult } from '../types';

// ─── Helpers ──────────────────────────────────────────────────────────────────

function fmt(v: number, decimals = 2): string {
  return v.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function fmtBig(v: number): string {
  if (v >= 1e12) return `$${(v / 1e12).toFixed(2)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  return `$${v.toLocaleString()}`;
}

// ─── Sort helpers ─────────────────────────────────────────────────────────────

type SortKey = keyof ScreenerResult;
type SortDir = 'asc' | 'desc';

function sortResults(results: ScreenerResult[], key: SortKey, dir: SortDir): ScreenerResult[] {
  return [...results].sort((a, b) => {
    const av = a[key] ?? 0;
    const bv = b[key] ?? 0;
    const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number);
    return dir === 'asc' ? cmp : -cmp;
  });
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function NumberInput({
  label,
  name,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  name: string;
  value: string;
  onChange: (val: string) => void;
  placeholder?: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs text-zinc-400">{label}</label>
      <input
        name={name}
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="bg-zinc-800 border border-zinc-700 rounded-md px-2 py-1.5 text-sm text-zinc-200 placeholder:text-zinc-600 focus:outline-none focus:border-blue-500 w-full"
      />
    </div>
  );
}

// ─── Results Table ────────────────────────────────────────────────────────────

interface ResultsTableProps {
  results: ScreenerResult[];
  onSelect: (symbol: string) => void;
}

function ResultsTable({ results, onSelect }: ResultsTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>('change_percent');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  }

  const sorted = sortResults(results, sortKey, sortDir);

  function SortIcon({ col }: { col: SortKey }) {
    if (col !== sortKey) return <Minus className="h-3 w-3 text-zinc-600" />;
    return sortDir === 'asc'
      ? <ChevronUp className="h-3 w-3 text-blue-400" />
      : <ChevronDown className="h-3 w-3 text-blue-400" />;
  }

  const cols: { key: SortKey; label: string; align: string }[] = [
    { key: 'symbol', label: 'Symbol', align: 'text-left' },
    { key: 'price', label: 'Price', align: 'text-right' },
    { key: 'change_percent', label: 'Change %', align: 'text-right' },
    { key: 'volume', label: 'Volume', align: 'text-right' },
    { key: 'market_cap', label: 'Mkt Cap', align: 'text-right' },
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-zinc-800">
            {cols.map((c) => (
              <th
                key={c.key}
                className={`pb-2 font-medium text-zinc-400 text-xs ${c.align} cursor-pointer hover:text-zinc-200 select-none`}
                onClick={() => handleSort(c.key)}
              >
                <span className={`inline-flex items-center gap-1 ${c.align === 'text-right' ? 'flex-row-reverse' : ''}`}>
                  {c.label}
                  <SortIcon col={c.key} />
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const up = r.change_percent >= 0;
            return (
              <tr
                key={r.symbol}
                className="border-b border-zinc-800/50 hover:bg-zinc-800/60 cursor-pointer transition-colors"
                onClick={() => onSelect(r.symbol)}
              >
                <td className="py-2.5 font-mono font-bold text-white">{r.symbol}</td>
                <td className="py-2.5 text-right text-zinc-200 tabular-nums">${fmt(r.price)}</td>
                <td className={`py-2.5 text-right font-medium tabular-nums ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                  {up ? '+' : ''}{fmt(r.change_percent)}%
                </td>
                <td className="py-2.5 text-right text-zinc-400 tabular-nums">
                  {r.volume !== undefined ? fmtBig(r.volume).replace('$', '') : '—'}
                </td>
                <td className="py-2.5 text-right text-zinc-400 tabular-nums">
                  {r.market_cap !== undefined ? fmtBig(r.market_cap) : '—'}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ─── Main Screener component ──────────────────────────────────────────────────

interface FilterState {
  assetType: AssetType;
  minPrice: string;
  maxPrice: string;
  minVolume: string;
  minChangePct: string;
  maxChangePct: string;
  limit: string;
}

const DEFAULT_FILTERS: FilterState = {
  assetType: 'stock',
  minPrice: '',
  maxPrice: '',
  minVolume: '',
  minChangePct: '',
  maxChangePct: '',
  limit: '50',
};

export function Screener() {
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const setActiveTab = useMarketStore((s) => s.setActiveTab);

  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [criteria, setCriteria] = useState<ScreenerCriteria | null>(null);

  const { data, isFetching, isError } = useScreener(criteria ?? { asset_type: 'stock' }, !!criteria);

  function patchFilter(patch: Partial<FilterState>) {
    setFilters((f) => ({ ...f, ...patch }));
  }

  function buildCriteria(): ScreenerCriteria {
    return {
      asset_type: filters.assetType,
      ...(filters.minPrice && { min_price: parseFloat(filters.minPrice) }),
      ...(filters.maxPrice && { max_price: parseFloat(filters.maxPrice) }),
      ...(filters.minVolume && { min_volume: parseInt(filters.minVolume, 10) }),
      ...(filters.minChangePct && { min_change_percent: parseFloat(filters.minChangePct) }),
      ...(filters.maxChangePct && { max_change_percent: parseFloat(filters.maxChangePct) }),
      limit: parseInt(filters.limit, 10) || 50,
    };
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setCriteria(buildCriteria());
  }

  function handleReset() {
    setFilters(DEFAULT_FILTERS);
    setCriteria(null);
  }

  function handleSelectSymbol(symbol: string) {
    setSelectedSymbol(symbol);
    setActiveTab('dashboard');
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-white">Market Screener</h2>
        <p className="text-sm text-zinc-400">Filter stocks and crypto by price, volume, and price change.</p>
      </div>

      {/* Filter form */}
      <form onSubmit={handleSubmit} className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-5">
        {/* Asset type toggle */}
        <div className="flex gap-2">
          {(['stock', 'crypto'] as AssetType[]).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => patchFilter({ assetType: t })}
              className={[
                'flex-1 py-1.5 rounded-lg text-sm font-medium capitalize transition-colors',
                filters.assetType === t
                  ? 'bg-blue-600 text-white'
                  : 'bg-zinc-800 text-zinc-400 hover:text-zinc-200',
              ].join(' ')}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <NumberInput label="Min Price ($)" name="minPrice" value={filters.minPrice}
            onChange={(v) => patchFilter({ minPrice: v })} placeholder="e.g. 10" />
          <NumberInput label="Max Price ($)" name="maxPrice" value={filters.maxPrice}
            onChange={(v) => patchFilter({ maxPrice: v })} placeholder="e.g. 1000" />
          <NumberInput label="Min Change %" name="minChangePct" value={filters.minChangePct}
            onChange={(v) => patchFilter({ minChangePct: v })} placeholder="e.g. 5" />
          <NumberInput label="Max Change %" name="maxChangePct" value={filters.maxChangePct}
            onChange={(v) => patchFilter({ maxChangePct: v })} placeholder="e.g. -5" />
          <NumberInput label="Min Volume" name="minVolume" value={filters.minVolume}
            onChange={(v) => patchFilter({ minVolume: v })} placeholder="e.g. 1000000" />
          <NumberInput label="Max Results" name="limit" value={filters.limit}
            onChange={(v) => patchFilter({ limit: v })} placeholder="50" />
        </div>

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={isFetching}
            className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg py-2 text-sm font-medium transition-colors"
          >
            {isFetching ? <Spinner size="sm" /> : <Search className="h-4 w-4" />}
            {isFetching ? 'Scanning…' : 'Screen'}
          </button>
          <button
            type="button"
            onClick={handleReset}
            className="px-4 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg py-2 text-sm font-medium transition-colors"
          >
            Reset
          </button>
        </div>
      </form>

      {/* Results */}
      {isError && (
        <div className="rounded-lg border border-red-800 bg-red-900/20 p-4 text-sm text-red-400">
          Failed to fetch screener results. Please try again.
        </div>
      )}

      {data && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-medium text-zinc-200">
              Results <span className="text-zinc-500 font-normal">({data.count})</span>
            </h3>
            <span className="text-xs text-zinc-500 capitalize">{filters.assetType}s</span>
          </div>
          {data.results.length === 0 ? (
            <p className="text-sm text-zinc-500 text-center py-6">No results matched your criteria.</p>
          ) : (
            <ResultsTable results={data.results} onSelect={handleSelectSymbol} />
          )}
        </div>
      )}
    </div>
  );
}
