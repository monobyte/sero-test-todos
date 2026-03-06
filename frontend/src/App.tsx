/**
 * Market Monitor – root application component
 *
 * Provides:
 * - QueryClientProvider  (React Query)
 * - Navigation tabs (Dashboard | Screener | Watchlist)
 * - Tab-based routing (no router dependency needed)
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useMarketStore } from './store/marketStore';
import { Dashboard } from './components/Dashboard';
import { Screener } from './components/Screener';
import { Watchlist } from './components/Watchlist';
import { BarChart2, Search, Star, Activity } from 'lucide-react';

// ─── React Query client ───────────────────────────────────────────────────────

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 2,
    },
  },
});

// ─── Navigation ───────────────────────────────────────────────────────────────

type Tab = 'dashboard' | 'screener' | 'watchlist';

const TABS: { id: Tab; label: string; icon: typeof BarChart2 }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: BarChart2 },
  { id: 'screener', label: 'Screener', icon: Search },
  { id: 'watchlist', label: 'Watchlist', icon: Star },
];

function Navigation() {
  const activeTab = useMarketStore((s) => s.activeTab);
  const setActiveTab = useMarketStore((s) => s.setActiveTab);

  return (
    <nav className="flex items-center gap-1">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          onClick={() => setActiveTab(id)}
          className={[
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            activeTab === id
              ? 'bg-blue-600 text-white'
              : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800',
          ].join(' ')}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </nav>
  );
}

// ─── Header ───────────────────────────────────────────────────────────────────

function Header() {
  return (
    <header className="border-b border-zinc-800 bg-zinc-950/80 backdrop-blur-sm sticky top-0 z-10">
      <div className="max-w-screen-xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <div className="flex items-center justify-center h-7 w-7 rounded-lg bg-blue-600">
            <Activity className="h-4 w-4 text-white" />
          </div>
          <span className="font-bold text-white text-sm tracking-tight">Market Monitor</span>
        </div>
        <Navigation />
      </div>
    </header>
  );
}

// ─── App Shell ────────────────────────────────────────────────────────────────

function AppShell() {
  const activeTab = useMarketStore((s) => s.activeTab);

  return (
    <div className="min-h-screen bg-[#0f0f0f]">
      <Header />
      <main className="max-w-screen-xl mx-auto px-6 py-6">
        {activeTab === 'dashboard' && <Dashboard />}
        {activeTab === 'screener' && <Screener />}
        {activeTab === 'watchlist' && <Watchlist />}
      </main>
    </div>
  );
}

// ─── Root ─────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppShell />
    </QueryClientProvider>
  );
}
