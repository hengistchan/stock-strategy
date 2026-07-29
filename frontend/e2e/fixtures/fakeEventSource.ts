import type { Page } from "@playwright/test";

interface BrowserEventSourceControl {
  emit: (type: string, payload: unknown) => void;
  instanceCount: () => number;
  openInstanceCount: () => number;
  urls: () => string[];
}

interface BrowserWithEventSourceControl extends Window {
  __strategyLabEventSourceControl?: BrowserEventSourceControl;
}

export async function installFakeEventSource(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type Listener = EventListenerOrEventListenerObject;

    class BrowserFakeEventSource {
      static readonly CONNECTING = 0;
      static readonly OPEN = 1;
      static readonly CLOSED = 2;

      readonly CONNECTING = BrowserFakeEventSource.CONNECTING;
      readonly OPEN = BrowserFakeEventSource.OPEN;
      readonly CLOSED = BrowserFakeEventSource.CLOSED;
      readonly url: string;
      readonly withCredentials: boolean;
      readyState = BrowserFakeEventSource.CONNECTING;
      onopen: ((event: Event) => void) | null = null;
      onmessage: ((event: MessageEvent<string>) => void) | null = null;
      onerror: ((event: Event) => void) | null = null;
      private readonly listeners = new Map<string, Set<Listener>>();

      constructor(url: string | URL, init?: EventSourceInit) {
        this.url = String(url);
        this.withCredentials = init?.withCredentials === true;
        instances.push(this);
        window.queueMicrotask(() => {
          if (this.readyState === BrowserFakeEventSource.CLOSED) return;
          this.readyState = BrowserFakeEventSource.OPEN;
          const event = new Event("open");
          this.onopen?.(event);
          this.dispatch("open", event);
        });
      }

      addEventListener(type: string, listener: Listener | null): void {
        if (!listener) return;
        const registered = this.listeners.get(type) ?? new Set<Listener>();
        registered.add(listener);
        this.listeners.set(type, registered);
      }

      removeEventListener(type: string, listener: Listener | null): void {
        if (!listener) return;
        this.listeners.get(type)?.delete(listener);
      }

      close(): void {
        this.readyState = BrowserFakeEventSource.CLOSED;
        this.listeners.clear();
      }

      emit(type: string, payload: unknown): void {
        if (this.readyState === BrowserFakeEventSource.CLOSED) return;
        const event = new MessageEvent<string>(type, {
          data: JSON.stringify(payload),
        });
        if (type === "message") this.onmessage?.(event);
        this.dispatch(type, event);
      }

      private dispatch(type: string, event: Event): void {
        for (const listener of this.listeners.get(type) ?? []) {
          if (typeof listener === "function") listener.call(this, event);
          else listener.handleEvent(event);
        }
      }
    }

    const instances: BrowserFakeEventSource[] = [];
    const controlledWindow = window as BrowserWithEventSourceControl;
    controlledWindow.__strategyLabEventSourceControl = {
      emit(type, payload) {
        for (const instance of instances) instance.emit(type, payload);
      },
      instanceCount: () => instances.length,
      openInstanceCount: () =>
        instances.filter(
          (instance) => instance.readyState !== BrowserFakeEventSource.CLOSED,
        ).length,
      urls: () => instances.map((instance) => instance.url),
    };
    Object.defineProperty(window, "EventSource", {
      configurable: true,
      writable: true,
      value: BrowserFakeEventSource,
    });
  });
}

export async function waitForEventSource(page: Page): Promise<void> {
  await page.waitForFunction(() => {
    const controlledWindow = window as BrowserWithEventSourceControl;
    return (
      controlledWindow.__strategyLabEventSourceControl?.openInstanceCount()
      ?? 0
    ) > 0;
  });
}

export async function emitApiEvent(
  page: Page,
  type: string,
  payload: unknown,
): Promise<void> {
  await page.evaluate(
    ({ eventType, eventPayload }) => {
      const controlledWindow = window as BrowserWithEventSourceControl;
      const control = controlledWindow.__strategyLabEventSourceControl;
      if (!control) throw new Error("Fake EventSource was not installed");
      control.emit(eventType, eventPayload);
    },
    { eventType: type, eventPayload: payload },
  );
}

export async function eventSourceUrls(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const controlledWindow = window as BrowserWithEventSourceControl;
    return controlledWindow.__strategyLabEventSourceControl?.urls() ?? [];
  });
}
