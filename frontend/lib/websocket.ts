type EventHandler = (data: any) => void;

class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private token: string | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelays = [1000, 2000, 4000, 8000, 16000, 30000];
  private handlers: Map<string, Set<EventHandler>> = new Map();

  constructor() {
    const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
    this.url = baseUrl.replace(/^http/, 'ws') + '/api/ws';
  }

  setToken(token: string) {
    this.token = token;
  }

  connect() {
    if (!this.token) return;
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return;

    this.ws = new WebSocket(`${this.url}?token=${this.token}`);

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      console.log('WebSocket connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        const { type, payload } = data;
        this.emit(type, payload);
      } catch (error) {
        console.error('Error parsing WS message', error);
      }
    };

    this.ws.onclose = () => {
      this.ws = null;
      this.scheduleReconnect();
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private scheduleReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts) {
      const delay = this.reconnectDelays[Math.min(this.reconnectAttempts, this.reconnectDelays.length - 1)];
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

  private emit(event: string, data: any) {
    if (this.handlers.has(event)) {
      this.handlers.get(event)!.forEach(handler => handler(data));
    }
  }
}

export const wsClient = new WebSocketClient();
