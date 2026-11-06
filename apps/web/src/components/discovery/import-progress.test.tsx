import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ImportProgress } from "@/components/discovery/import-progress";
import { importDetail } from "@/components/discovery/test-fixtures";

const running = importDetail({ status: "running", total_rows: 200, processed_rows: 50 });

async function tick() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1600);
  });
}

describe("ImportProgress", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows how far the import has got", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ImportProgress batch={running} onChange={vi.fn()} />);

    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "25");
    expect(screen.getByText("50 of 200 rows processed")).toBeInTheDocument();
  });

  it("says when it is still waiting for a worker", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<ImportProgress batch={importDetail({ status: "queued" })} onChange={vi.fn()} />);

    expect(screen.getByText("Waiting for a worker")).toBeInTheDocument();
  });

  it("polls and passes on updates", async () => {
    const next = importDetail({ status: "completed", processed_rows: 200, total_rows: 200 });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(next)));
    vi.stubGlobal("fetch", fetchMock);
    const onChange = vi.fn();
    render(<ImportProgress batch={running} onChange={onChange} />);

    await tick();

    expect(fetchMock).toHaveBeenCalledWith(`/api/imports/${running.id}`, { cache: "no-store" });
    expect(onChange).toHaveBeenCalledWith(next);
  });

  it("keeps trying through brief failures, then says updates stopped", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<ImportProgress batch={running} onChange={vi.fn()} />);

    await tick();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    for (let i = 0; i < 5; i += 1) await tick();
    expect(screen.getByRole("alert")).toHaveTextContent(/updates stopped/i);
  });

  it("stops polling when removed", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(running)));
    vi.stubGlobal("fetch", fetchMock);
    const { unmount } = render(<ImportProgress batch={running} onChange={vi.fn()} />);

    unmount();
    await tick();

    expect(fetchMock).not.toHaveBeenCalled();
  });
});
