/**
 * Dashboard – the main view: selected-symbol detail panel + mini watchlist sidebar.
 */
import { useMarketStore } from '../store/marketStore';
import { QuoteCard, AddSymbolCard } from './QuoteCard';
import { HistoricalChart } from './HistoricalChart';
import { useWebSocket } from '../hooks/useWebSocket';
import { Wifi, WifiOff } from 'lucide-react';

// ─── Symbol detail panel ──────────────────────────────────────────────────────

function SymbolDetailPanel({ symbol }: { symbol: string }) {
  return (
    <div className="flex-1 space-y-4">
      {/* Quote card – full size */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5 space-y-4">
        <QuoteCard symbol={symbol} compact={false} />
      </div>

      {/* Historical chart */}
      <div className="rounded-xl border border-zinc-800 bg-zinc-900 p-5">
        <h3 className="text-sm font-medium text-zinc-300 mb-4">Price History</h3>
        <HistoricalChart symbol={symbol} />
      </div>
    </div>
  );
}

// ─── Sidebar watchlist ────────────────────────────────────────────────────────

function SidebarWatchlist() {
  const watchlist = useMarketStore((s) => s.watchlist);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);
  const addToWatchlist = useMarketStore((s) => s.addToWatchlist);

  return (
    <aside className="w-72 shrink-0 space-y-3">
      <h3 className="text-xs font-medium text-zinc-500 uppercase tracking-wider px-1">Watchlist</h3>
      <div className="space-y-2">
        {watchlist.map((item) => (
          <QuoteCard
            key={item.symbol}
            symbol={item.symbol}
            compact
            selected={selectedSymbol === item.symbol}
            onClick={() => setSelectedSymbol(item.symbol)}
          />
        ))}
        <AddSymbolCard onAdd={(sym) => addToWatchlist(sym)} />
      </div>
    </aside>
  );
}

// ─── WS status badge ─────────────────────────────────────────────────────────

function WsStatusBadge() {
  const connected = useMarketStore((s) => s.wsConnected);
  return (
    <div className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full ${connected ? 'text-emerald-400 bg-emerald-400/10' : 'text-zinc-500 bg-zinc-800'}`}>
      {connected ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
      {connected ? 'Live' : 'Polling'}
    </div>
  );
}

// ─── Main Dashboard ───────────────────────────────────────────────────────────

export function Dashboard() {
  const watchlist = useMarketStore((s) => s.watchlist);
  const selectedSymbol = useMarketStore((s) => s.selectedSymbol);
  const setSelectedSymbol = useMarketStore((s) => s.setSelectedSymbol);

  // Subscribe to all watchlist symbols via WebSocket
  const symbols = watchlist.map((w) => w.symbol);
  useWebSocket({ symbols, enabled: symbols.length > 0 });

  // Auto-select first symbol if none selected
  if (!selectedSymbol && watchlist.length > 0 && watchlist[0]) {
    setSelectedSymbol(watchlist[0].symbol);
  }

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-white">Dashboard</h2>
          <p className="text-xs text-zinc-500">Real-time market overview</p>
        </div>
        <WsStatusBadge />
      </div>

      {/* Layout */}
      <div className="flex gap-5">
        {/* Main panel */}
        {selectedSymbol ? (
          <SymbolDetailPanel symbol={selectedSymbol} />
        ) : (
          <div className="flex-1 flex items-center justify-center h-64 rounded-xl border border-dashed border-zinc-800 text-zinc-500 text-sm">
            Select a symbol to view details
          </div>
        )}

        {/* Sidebar */}
        <SidebarWatchlist />
      </div>
    </div>
  );
}
