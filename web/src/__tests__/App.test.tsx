import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { jsonResponse, modeSummaryFixture, summaryFixture } from "./fixtures";

function serve(...responses: (() => Response)[]) {
  let call = 0;
  const fetchMock = vi.fn((_url: string) => Promise.resolve(responses[Math.min(call++, responses.length - 1)]!()));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("loads the summary, then shows tiers, the table and the most-played hero", async () => {
    const fetchMock = serve(() => jsonResponse(summaryFixture()));
    render(<App />);
    expect(screen.getByText(/Loading hero statistics/)).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "Abrams" })).toBeInTheDocument();
    expect(screen.getByText("Up to date.")).toBeInTheDocument();
    expect(screen.getByText(/Not enough games yet: Bebop, Haze/)).toBeInTheDocument();
    expect(await screen.findByText("Win rate by day")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toBe("/data/summary.json");
  });

  it("recomputes totals when the date range changes, without refetching", async () => {
    const fetchMock = serve(() => jsonResponse(summaryFixture()));
    const user = userEvent.setup();
    render(<App />);
    await user.selectOptions(await screen.findByRole("combobox", { name: "From" }), "2026-10-06");
    expect(screen.getByText(/over 1 day/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Bebop/ })).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("says when a selected day has a hole in the source data, and only then", async () => {
    const base = summaryFixture();
    serve(() =>
      jsonResponse(summaryFixture({ coverage: { ...base.coverage, gap_minutes_by_date: { "2026-10-06": 8 } } })),
    );
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByText(/missing 8 min on 2026-10-06/)).toBeInTheDocument();
    await user.selectOptions(screen.getByRole("combobox", { name: "To" }), "2026-10-05");
    expect(screen.queryByText(/missing 8 min/)).not.toBeInTheDocument();
  });

  it("warns when the data is old", async () => {
    const old = new Date(Date.now() - 5 * 3_600_000).toISOString();
    serve(() => jsonResponse(summaryFixture({ built_at: old })));
    render(<App />);
    expect(await screen.findByText("Data is stale.")).toBeInTheDocument();
  });

  it("treats 'nothing published yet' as an empty state, not an error", async () => {
    serve(() => new Response("AccessDenied", { status: 403 }));
    render(<App />);
    expect(await screen.findByText("No complete day of data yet.")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows an error with a working retry", async () => {
    serve(() => new Response("oops", { status: 500 }), () => jsonResponse(summaryFixture()));
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent("500");
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("heading", { name: "Abrams" })).toBeInTheDocument();
  });

  it("filters by role and moves the panel to a hero in that role", async () => {
    serve(() => jsonResponse(summaryFixture()));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Abrams" });
    await user.click(screen.getByRole("button", { name: "Assassin" }));
    expect(screen.getByRole("heading", { name: "Haze" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Abrams/ })).not.toBeInTheDocument();
  });

  it("switches between ranked, unranked and all matches", async () => {
    serve(() => jsonResponse(modeSummaryFixture()));
    const user = userEvent.setup();
    render(<App />);
    await screen.findByRole("heading", { name: "Abrams" });
    const sample = () => screen.getByText(/matches over/).textContent;
    expect(sample()).toMatch(/^500 matches/);
    await user.click(screen.getByRole("button", { name: "Unranked" }));
    expect(sample()).toMatch(/^100 matches/);
    expect(screen.queryByRole("button", { name: /Bebop/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Ranked" }));
    expect(sample()).toMatch(/^400 matches/);
    await user.click(screen.getByRole("button", { name: "All matches" }));
    expect(sample()).toMatch(/^500 matches/);
  });

  it("hides the mode toggle for a summary that isn't split by mode", async () => {
    serve(() => jsonResponse(summaryFixture()));
    render(<App />);
    await screen.findByRole("heading", { name: "Abrams" });
    expect(screen.queryByRole("group", { name: "Match mode" })).not.toBeInTheDocument();
  });
});
