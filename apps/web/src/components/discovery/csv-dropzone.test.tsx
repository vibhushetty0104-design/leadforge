import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CsvDropzone } from "@/components/discovery/csv-dropzone";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function csv(name = "leads.csv", content = "name\nAcme\n") {
  return new File([content], name, { type: "text/csv" });
}

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("CsvDropzone", () => {
  beforeEach(() => {
    push.mockClear();
    vi.unstubAllGlobals();
  });

  it("uploads the chosen file and opens the import", async () => {
    const fetchMock = stubFetch(201, { id: "abc" });
    render(<CsvDropzone />);

    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv("my leads.csv"));

    await waitFor(() => expect(push).toHaveBeenCalledWith("/discovery/imports/abc"));
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/api/imports?filename=my%20leads.csv");
    expect(init.method).toBe("POST");
  });

  it("accepts a dropped file", async () => {
    stubFetch(201, { id: "dropped" });
    render(<CsvDropzone />);

    fireEvent.drop(screen.getByText(/Drop a CSV here/), { dataTransfer: { files: [csv()] } });

    await waitFor(() => expect(push).toHaveBeenCalledWith("/discovery/imports/dropped"));
  });

  it("rejects a non-CSV file without uploading", async () => {
    const fetchMock = stubFetch(201, { id: "never" });
    render(<CsvDropzone />);

    fireEvent.drop(screen.getByText(/Drop a CSV here/), {
      dataTransfer: { files: [new File(["x"], "leads.xlsx")] },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(".csv");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the server's explanation when an upload is refused", async () => {
    stubFetch(422, { error: { message: "Line 3 is malformed." } });
    render(<CsvDropzone />);

    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv());

    expect(await screen.findByRole("alert")).toHaveTextContent("Line 3 is malformed.");
    expect(push).not.toHaveBeenCalled();
  });

  it("reports a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<CsvDropzone />);

    await userEvent.upload(screen.getByLabelText("Choose a CSV file"), csv());

    expect(await screen.findByRole("alert")).toHaveTextContent(/upload failed/i);
  });
});
