/**
 * HistoricalChart – Recharts area chart for OHLCV historical data.
 * Supports multiple time ranges and displays price + volume.
 */
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  ComposedChart,
  type TooltipProps,
} from 'recharts';
import { Spinner } from './ui/Spinner';
import { useHistoricalByTimeRange } from '../hooks/useHistorical';
import { useMarketStore } from '../store/marketStore';
import type { TimeRange, Candle } from '../types';

const TIME_RANGES: TimeRange[] = ['1D', '1W', '1M', '3M', '6M', '1Y'];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatDate(ts: string, range: TimeRange): string {
  const d = new Date(ts);
  if (range === '1D') return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  if (range === '1W') return d.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatVolume(v: number): string {
  if (v >= 1e9) return `${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `${(v / 1e6).toFixed(1)}M`;
  if (v >= 1e3) return `${(v / 1e3).toFixed(1)}K`;
  return String(v);
}

function formatPrice(v: number): string {
  if (v >= 1000) return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (v >= 1) return v.toFixed(2);
  return v.toFixed(6);
}

// ─── Custom Tooltip ───────────────────────────────────────────────────────────

interface ChartDatum {
  ts: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

function CustomTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload as ChartDatum;
  const isUp = d.close >= d.open;
  return (
    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-3 text-xs shadow-xl">
      <div className="text-zinc-400 mb-2">{label}</div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        <span className="text-zinc-400">Open</span>
        <span className="text-zinc-100 text-right">${formatPrice(d.open)}</span>
        <span className="text-zinc-400">High</span>
        <span className="text-emerald-400 text-right">${formatPrice(d.high)}</span>
        <span className="text-zinc-400">Low</span>
        <span className="text-red-400 text-right">${formatPrice(d.low)}</span>
        <span className="text-zinc-400">Close</span>
        <span className={`text-right font-bold ${isUp ? 'text-emerald-400' : 'text-red-400'}`}>
          ${formatPrice(d.close)}
        </span>
        <span className="text-zinc-400">Volume</span>
        <span className="text-zinc-300 text-right">{formatVolume(d.volume)}</span>
      </div>
    </div>
  );
}

// ─── Empty State ──────────────────────────────────────────────────────────────

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center h-48 text-sm text-zinc-500">
      {message}
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

interface HistoricalChartProps {
  symbol: string | null;
}

export function HistoricalChart({ symbol }: HistoricalChartProps) {
  const selectedTimeRange = useMarketStore((s) => s.selectedTimeRange);
  const setSelectedTimeRange = useMarketStore((s) => s.setSelectedTimeRange);
  const { data, isLoading, isError } = useHistoricalByTimeRange(symbol, selectedTimeRange);

  // Derive chart colour from first vs last candle
  const candles: Candle[] = data?.candles ?? [];
  const isPositive = candles.length >= 2
    ? candles[candles.length - 1].close >= candles[0].close
    : true;

  const strokeColor = isPositive ? '#34d399' : '#f87171';
  const gradientId = `area-gradient-${symbol}`;

  const chartData: ChartDatum[] = candles.map((c) => ({
    ts: formatDate(c.timestamp, selectedTimeRange),
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close,
    volume: c.volume,
  }));

  // Determine Y-axis domain with a little padding
  const prices = candles.flatMap((c) => [c.high, c.low]);
  const minPrice = prices.length ? Math.min(...prices) : 0;
  const maxPrice = prices.length ? Math.max(...prices) : 1;
  const padding = (maxPrice - minPrice) * 0.05 || maxPrice * 0.05;
  const yDomain: [number, number] = [minPrice - padding, maxPrice + padding];

  return (
    <div className="flex flex-col gap-3">
      {/* Time range selector */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setSelectedTimeRange(r)}
              className={[
                'px-2.5 py-1 rounded-md text-xs font-medium transition-colors',
                selectedTimeRange === r
                  ? 'bg-blue-600 text-white'
                  : 'text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800',
              ].join(' ')}
            >
              {r}
            </button>
          ))}
        </div>
        {data && (
          <span className="text-xs text-zinc-500">
            {data.count} candles · {data.interval} · via {data.source}
          </span>
        )}
      </div>

      {/* Chart area */}
      {isLoading ? (
        <div className="flex items-center justify-center h-48">
          <Spinner />
        </div>
      ) : isError ? (
        <EmptyState message="Failed to load historical data" />
      ) : chartData.length === 0 ? (
        <EmptyState message={symbol ? 'No data available for this range' : 'Select a symbol to view chart'} />
      ) : (
        <div className="space-y-1">
          {/* Price chart */}
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={strokeColor} stopOpacity={0.25} />
                  <stop offset="100%" stopColor={strokeColor} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
              <XAxis
                dataKey="ts"
                tick={{ fill: '#71717a', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={yDomain}
                tick={{ fill: '#71717a', fontSize: 10 }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => `$${formatPrice(v)}`}
                width={68}
              />
              <Tooltip content={<CustomTooltip />} cursor={{ stroke: '#52525b', strokeWidth: 1 }} />
              <Area
                type="monotone"
                dataKey="close"
                stroke={strokeColor}
                strokeWidth={1.5}
                fill={`url(#${gradientId})`}
                dot={false}
                activeDot={{ r: 4, fill: strokeColor, strokeWidth: 0 }}
              />
            </ComposedChart>
          </ResponsiveContainer>

          {/* Volume chart */}
          <ResponsiveContainer width="100%" height={60}>
            <BarChart data={chartData} margin={{ top: 0, right: 8, left: 0, bottom: 0 }}>
              <YAxis hide domain={['auto', 'auto']} />
              <XAxis dataKey="ts" hide />
              <Bar dataKey="volume" fill="#3f3f46" radius={[1, 1, 0, 0]} maxBarSize={12} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
