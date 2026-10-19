import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HeroTable, sortHeroes } from "../components/HeroTable";
import { heroTotals } from "../summary";
import { summaryFixture } from "./fixtures";

const rows = heroTotals(summaryFixture(), ["2026-10-05", "2026-10-06"]);

function heroOrder() {
  return within(screen.getAllByRole("rowgroup")[1]!)
    .getAllByRole("rowheader")
    .map((cell) => cell.querySelector(".hero-name")!.firstChild!.textContent);
}

describe("HeroTable", () => {
  it("defaults to most games first and shows names, roles and tiers", () => {
    render(<HeroTable rows={rows} selected={15} onSelect={() => {}} />);
    expect(heroOrder()).toEqual(["Abrams", "Bebop", "Haze"]);
    expect(screen.getByRole("columnheader", { name: /Games/ })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByLabelText("tier S")).toBeInTheDocument(); // 90/150 for Abrams
    expect(screen.getAllByText("Brawler")).toHaveLength(2);
    expect(screen.getByRole("button", { name: /Bebop/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("sorts by a column and toggles direction", async () => {
    const user = userEvent.setup();
    render(<HeroTable rows={rows} selected={null} onSelect={() => {}} />);
    await user.click(screen.getByRole("button", { name: /Win rate/ }));
    expect(heroOrder()).toEqual(["Haze", "Abrams", "Bebop"]);
    await user.click(screen.getByRole("button", { name: /Win rate/ }));
    expect(heroOrder()).toEqual(["Bebop", "Abrams", "Haze"]);
    await user.click(screen.getByRole("button", { name: /^Hero/ }));
    expect(heroOrder()).toEqual(["Abrams", "Bebop", "Haze"]);
  });

  it("keeps nulls last in both directions", () => {
    expect(sortHeroes(rows, "avg_duration_s", "descending").at(-1)!.name).toBe("Haze");
    expect(sortHeroes(rows, "avg_duration_s", "ascending").at(-1)!.name).toBe("Haze");
  });

  it("shows a dash for an average it can't compute", () => {
    render(<HeroTable rows={rows} selected={null} onSelect={() => {}} />);
    const row = screen.getByRole("button", { name: /Haze/ }).closest("tr")!;
    expect(within(row).getAllByText("—").length).toBeGreaterThan(0);
  });

  it("selects a hero with the keyboard", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<HeroTable rows={rows} selected={null} onSelect={onSelect} />);
    screen.getByRole("button", { name: /Haze/ }).focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(13);
  });
});
