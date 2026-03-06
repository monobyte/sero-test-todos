/**
 * WebSocket hook for real-time quote updates
 *
 * Connects to /ws/quotes, subscribes to the given symbols,
 * dispatches updates to the Zustand store, and handles
 * reconnection with exponential back-off.
 */
import { useEffect, useRef, useCallback } from 'react';
import { createQuotesWebSocket } from '../api/client';
import { useMarketStore } from '../store/marketStore';
import type { WsMessage, WsSubscribeAction } from '../types';

interface UseWebSocketOptions {
  symbols: string[];
  enabled?: boolean;
}

const MAX_RETRIES = 6;
const BASE_DELAY_MS = 1_000;

export function useWebSocket({ symbols, enabled = true }: UseWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const retriesRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const symbolsRef = useRef<string[]>(symbols);
  const mountedRef = useRef(true);

  const updateLiveQuote = useMarketStore((s) => s.updateLiveQuote);
  const setWsConnected = useMarketStore((s) => s.setWsConnected);

  // Keep latest symbols list without re-running the effect
  useEffect(() => {
    symbolsRef.current = symbols;
  }, [symbols]);

  const subscribe = useCallback((ws: WebSocket) => {
    if (symbolsRef.current.length === 0) return;
    const msg: WsSubscribeAction = { action: 'subscribe', symbols: symbolsRef.current };
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(msg));
    }
  }, []);

  const connect = useCallback(() => {
    if (!mountedRef.current || !enabled) return;

    const ws = createQuotesWebSocket();
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      retriesRef.current = 0;
      setWsConnected(true);
      subscribe(ws);
    };

    ws.onmessage = (event: MessageEvent<string>) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage;

        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }));
          return;
        }

        if (msg.type === 'quote') {
          updateLiveQuote(msg.symbol, {
            price: msg.price,
            change: msg.change,
            change_percent: msg.change_percent,
            volume: msg.volume,
            timestamp: msg.timestamp,
          });
        }
        // 'error' messages are silently ignored – REST fallback covers them
      } catch {
        // Malformed JSON – ignore
      }
    };

    ws.onclose = () => {
      setWsConnected(false);
      if (!mountedRef.current || !enabled) return;
      if (retriesRef.current >= MAX_RETRIES) return;

      const delay = BASE_DELAY_MS * 2 ** retriesRef.current;
      retriesRef.current += 1;
      reconnectTimerRef.current = setTimeout(connect, delay);
    };

    ws.onerror = () => {
      // onclose fires right after, which handles reconnect
    };
  }, [enabled, subscribe, updateLiveQuote, setWsConnected]);

  // Reconnect when symbols list changes
  const resubscribe = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      subscribe(wsRef.current);
    }
  }, [subscribe]);

  // Initial connection
  useEffect(() => {
    mountedRef.current = true;
    if (enabled && symbols.length > 0) {
      connect();
    }
    return () => {
      mountedRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      setWsConnected(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);

  // Re-subscribe when symbol list changes (without full reconnect)
  useEffect(() => {
    resubscribe();
  }, [symbols.join(','), resubscribe]); // eslint-disable-line react-hooks/exhaustive-deps
}
