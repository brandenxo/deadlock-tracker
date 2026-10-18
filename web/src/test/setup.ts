import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());

// jsdom has no layout engine and no ResizeObserver. Recharts' ResponsiveContainer
// needs the API to exist; with zero size it simply renders no SVG, which is why the
// tests assert on the table view of the chart rather than on pixels.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;
