/**
 * QuoteCard – displays real-time price, change, and key stats for a symbol.
 * Merges REST data with live WebSocket updates from the Zustand store.
 */
import { TrendingUp, TrendingDown, Minus, Plus, X, Star } from 'lucide-react';
import { Spinner } from './ui/Spinner';
import { Badge } from './ui/Badge';
import { useQuote } from '../hooks/useQuotes';
import { useMarketStore } from '../store/marketStore';
import type { Quote } from '../types';

interface QuoteCardProps {
  symbol: string;
  onClick?: () => void;
  selected?: boolean;
  compact?: boolean;
  onRemove?: () => void;
}

function formatPrice(price: number): string {
  if (price >= 1000) return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price >= 1) return price.toFixed(2);
  return price.toFixed(6);
}

function formatVolume(volume?: number | null): string {
  if (volume == null) return '—';
  if (volume >= 1e12) return `${(volume / 1e12).toFixed(2)}T`;
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(2)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(2)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toLocaleString();
}

function formatPercent(pct: number): string {
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`;
}

function ChangeIndicator({ changePct }: { changePct: number }) {
  if (changePct > 0)
    return (
      <span className="flex items-center gap-0.5 text-emerald-400 font-medium">
        <TrendingUp className="h-3.5 w-3.5" />
        {formatPercent(changePct)}
      </span>
    );
  if (changePct < 0)
    return (
      <span className="flex items-center gap-0.5 text-red-400 font-medium">
        <TrendingDown className="h-3.5 w-3.5" />
        {formatPercent(changePct)}
      </span>
    );
  return (
    <span className="flex items-center gap-0.5 text-zinc-400 font-medium">
      <Minus className="h-3.5 w-3.5" />
      {formatPercent(changePct)}
    </span>
  );
}

function QuoteCardContent({
  quote,
  liveUpdate,
  compact,
}: {
  quote: Quote;
  liveUpdate: Partial<Quote> | undefined;
  compact: boolean;
}) {
  const price = liveUpdate?.price ?? quote.price;
  const change = liveUpdate?.change ?? quote.change ?? 0;
  const changePct = liveUpdate?.change_percent ?? quote.change_percent ?? 0;

  return (
    <>
      {/* Price row */}
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-white tabular-nums">
          ${formatPrice(price)}
        </span>
        <ChangeIndicator changePct={changePct} />
      </div>

      {/* Change value */}
      <div className={`text-xs ${change >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
        {change >= 0 ? '+' : ''}
        {change.toFixed(2)} today
      </div>

      {!compact && (
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-zinc-400">
          {quote.volume !== undefined && (
            <>
              <span>Volume</span>
              <span className="text-zinc-300 text-right">{formatVolume(quote.volume)}</span>
            </>
          )}
          {quote.high !== undefined && (
            <>
              <span>High</span>
              <span className="text-zinc-300 text-right">${formatPrice(quote.high)}</span>
            </>
          )}
          {quote.low !== undefined && (
            <>
              <span>Low</span>
              <span className="text-zinc-300 text-right">${formatPrice(quote.low)}</span>
            </>
          )}
          {quote.market_cap !== undefined && (
            <>
              <span>Mkt Cap</span>
              <span className="text-zinc-300 text-right">{formatVolume(quote.market_cap)}</span>
            </>
          )}
          <span>Source</span>
          <span className="text-zinc-300 text-right capitalize">{quote.source}</span>
        </div>
      )}
    </>
  );
}

export function QuoteCard({ symbol, onClick, selected = false, compact = false, onRemove }: QuoteCardProps) {
  const { data: quote, isLoading, isError, error } = useQuote(symbol);
  const liveQuotes = useMarketStore((s) => s.liveQuotes);
  const addToWatchlist = useMarketStore((s) => s.addToWatchlist);
  const removeFromWatchlist = useMarketStore((s) => s.removeFromWatchlist);
  const isInWatchlist = useMarketStore((s) => s.isInWatchlist);

  const liveUpdate = liveQuotes[symbol];
  const inWatchlist = isInWatchlist(symbol);

  const baseClass = [
    'relative rounded-xl border p-4 transition-all duration-150 cursor-pointer group',
    'bg-zinc-900 hover:bg-zinc-800',
    selected
      ? 'border-blue-500 ring-1 ring-blue-500/30'
      : 'border-zinc-800 hover:border-zinc-700',
  ].join(' ');

  return (
    <div data-testid="quote-card" className={baseClass} onClick={onClick} role="button" tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onClick?.()}>

      {/* Header row */}
      <div className="flex items-start justify-between mb-2">
        <div>
          <span className="font-mono font-bold text-white text-sm tracking-wide">{symbol.toUpperCase()}</span>
          {quote?.asset_type && (
            <Badge variant={quote.asset_type === 'crypto' ? 'warning' : 'info'} className="ml-2">
              {quote.asset_type}
            </Badge>
          )}
          {liveUpdate && (
            <span className="ml-2 inline-flex items-center">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
            </span>
          )}
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button
            onClick={(e) => {
              e.stopPropagation();
              inWatchlist ? removeFromWatchlist(symbol) : addToWatchlist(symbol, quote?.asset_type);
            }}
            className="p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-amber-400 transition-colors"
            title={inWatchlist ? 'Remove from watchlist' : 'Add to watchlist'}
          >
            <Star className={`h-3.5 w-3.5 ${inWatchlist ? 'fill-amber-400 text-amber-400' : ''}`} />
          </button>
          {onRemove && (
            <button
              onClick={(e) => { e.stopPropagation(); onRemove(); }}
              className="p-1 rounded hover:bg-zinc-700 text-zinc-400 hover:text-red-400 transition-colors"
              title="Remove"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      {isLoading ? (
        <div className="flex items-center justify-center py-4">
          <Spinner size="sm" />
        </div>
      ) : isError ? (
        <div data-testid="quote-error" className="text-xs text-red-400 py-2">
          {(error as Error)?.message ?? 'Failed to load quote'}
        </div>
      ) : quote ? (
        <QuoteCardContent quote={quote} liveUpdate={liveUpdate} compact={compact} />
      ) : null}
    </div>
  );
}

/** Compact add-symbol input card */
export function AddSymbolCard({ onAdd }: { onAdd: (symbol: string) => void }) {
  return (
    <div className="rounded-xl border border-dashed border-zinc-700 p-4 hover:border-zinc-500 transition-colors">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          const fd = new FormData(e.currentTarget);
          const sym = (fd.get('symbol') as string).trim().toUpperCase();
          if (sym) { onAdd(sym); (e.target as HTMLFormElement).reset(); }
        }}
        className="flex gap-2 items-center"
      >
        <Plus className="h-4 w-4 text-zinc-500 shrink-0" />
        <input
          name="symbol"
          placeholder="Add symbol…"
          className="flex-1 bg-transparent text-sm text-zinc-300 placeholder:text-zinc-600 outline-none"
          autoComplete="off"
        />
        <button type="submit" className="text-xs text-blue-400 hover:text-blue-300 shrink-0">
          Add
        </button>
      </form>
    </div>
  );
}
