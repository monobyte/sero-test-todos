/**
 * Watchlist panel – lists watched symbols, lets user select one, and add/remove.
 */
import { Star } from 'lucide-react';
import { QuoteCard, AddSymbolCard } from './QuoteCard';
import { useMarketStore } from '../store/marketStore';

export function Watchlist() {
  const watchlist = useMarketStore((s) => s.watchlist);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const addToWatchlist = useMarketStore((s) => s.addToWatchlist);
  const removeFromWatchlist = useMarketStore((s) => s.removeFromWatchlist);
  const setActiveTab = useMarketStore((s) => s.setActiveTab);

  function handleSelect(symbol: string) {
    setSelectedSymbol(symbol);
    setActiveTab('dashboard');
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Star className="h-4 w-4 text-amber-400" />
        <h2 className="text-lg font-semibold text-white">Watchlist</h2>
        <span className="text-zinc-500 text-sm">({watchlist.length})</span>
      </div>

      {watchlist.length === 0 ? (
        <div className="rounded-xl border border-dashed border-zinc-700 p-8 text-center">
          <Star className="h-8 w-8 text-zinc-600 mx-auto mb-2" />
          <p className="text-zinc-500 text-sm">Your watchlist is empty.</p>
          <p className="text-zinc-600 text-xs mt-1">Add symbols using the input below or the ★ button on any quote card.</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {watchlist.map((item) => (
            <QuoteCard
              key={item.symbol}
              symbol={item.symbol}
              selected={selectedSymbol === item.symbol}
              onClick={() => handleSelect(item.symbol)}
              onRemove={() => removeFromWatchlist(item.symbol)}
            />
          ))}
        </div>
      )}

      <AddSymbolCard onAdd={(sym) => addToWatchlist(sym)} />
    </div>
  );
}
