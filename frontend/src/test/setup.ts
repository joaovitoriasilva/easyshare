import { beforeEach, vi } from "vitest";

// Provide a minimal localStorage implementation for jsdom-based tests.
class LocalStorageMock {
  private store: Record<string, string> = {};

  getItem(key: string): string | null {
    return key in this.store ? this.store[key] : null;
  }

  setItem(key: string, value: string): void {
    this.store[key] = value;
  }

  removeItem(key: string): void {
    delete this.store[key];
  }

  clear(): void {
    this.store = {};
  }
}

vi.stubGlobal("localStorage", new LocalStorageMock());

beforeEach(() => {
  localStorage.clear();
});
