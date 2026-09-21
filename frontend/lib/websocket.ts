type EventHandler = (data: unknown) => void;
export type ConnectionState = 'CONNECTED' | 'CONNECTING' | 'RECONNECTING' | 'DISCONNECTED';

class WebSocketClient {
  private ws: WebSocket | null = null;
  private token: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseDelays = [1000, 2000, 3000, 5000, 8000, 10000];
  private handlers: Map<string, Set<EventHandler>> = new Map();
  private state: ConnectionState = 'DISCONNECTED';
  private stateListeners: Set<(state: ConnectionState) => void> = new Set();
  private wasReconnecting = false;

  setToken(token: string) {
    this.token = token;
  }

  getState(): ConnectionState {
    return this.state;
  }

  onStateChange(cb: (state: ConnectionState) => void): () => void {
    this.stateListeners.add(cb);
    cb(this.state);
    return () => this.stateListeners.delete(cb);
  }

  private setState(newState: ConnectionState) {
    this.state = newState;
    this.stateListeners.forEach(listener => listener(newState));
  }

  getWsUrl(): string {
    if (process.env.NEXT_PUBLIC_WS_URL) {
      return process.env.NEXT_PUBLIC_WS_URL;
    }
    if (process.env.NEXT_PUBLIC_API_URL) {
      const base = process.env.NEXT_PUBLIC_API_URL.replace(/\/$/, '');
      const wsProto = base.startsWith('https:') ? 'wss:' : 'ws:';
      const hostPart = base.replace(/^https?:\/\//, '');
      return `${wsProto}//${hostPart}/api/ws`;
    }
    if (typeof window !== 'undefined') {
      const host = window.location.hostname || 'localhost';
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      return `${wsProto}//${host}:8000/api/ws`;
    }
    return 'ws://localhost:8000/api/ws';
  }

  connect() {
    if (typeof window === 'undefined' || !this.token) return;
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return;

    try {
      if (this.reconnectAttempts > 0) {
        this.wasReconnecting = true;
        this.setState('RECONNECTING');
      } else {
        this.setState('CONNECTING');
      }
      const baseWs = this.getWsUrl();
      const wsUrl = `${baseWs}?token=${encodeURIComponent(this.token)}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        const wasReconnect = this.wasReconnecting;
        this.reconnectAttempts = 0;
        this.wasReconnecting = false;
        this.setState('CONNECTED');
        if (wasReconnect) {
          this.emit('RECONNECTED', {});
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const parsed = JSON.parse(event.data as string);
          const eventType = parsed.type || parsed.event;
          const eventPayload = parsed.payload !== undefined ? parsed.payload : (parsed.data !== undefined ? parsed.data : parsed);
          if (eventType) {
            this.emit(eventType, eventPayload);
          }
        } catch {
          // ignore non-json messages
        }
      };

      this.ws.onerror = () => {
        // Handled in onclose
      };

      this.ws.onclose = () => {
        this.ws = null;
        this.setState('DISCONNECTED');
        this.scheduleReconnect();
      };
    } catch {
      this.setState('DISCONNECTED');
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const baseDelay = this.baseDelays[Math.min(this.reconnectAttempts, this.baseDelays.length - 1)];
      const jitter = (Math.random() - 0.5) * 0.6 * baseDelay;
      const delay = Math.max(500, baseDelay + jitter);
      setTimeout(() => this.connect(), delay);
      this.reconnectAttempts++;
    }
  }

  on(event: string, handler: EventHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
  }

  off(event: string, handler: EventHandler) {
    if (this.handlers.has(event)) {
      this.handlers.get(event)!.delete(handler);
    }
  }

  subscribe(event: string, handler: EventHandler): () => void {
    this.on(event, handler);
    return () => this.off(event, handler);
  }

  private emit(event: string, data: unknown) {
    if (this.handlers.has(event)) {
      this.handlers.get(event)!.forEach(handler => handler(data));
    }
  }
}

export const wsClient = new WebSocketClient();
