import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { cancelImportAction, saveImportMappingAction } from "@/app/actions";
import { ColumnMapper } from "@/components/discovery/column-mapper";
import { importDetail } from "@/components/discovery/test-fixtures";

vi.mock("@/app/actions", () => ({
  saveImportMappingAction: vi.fn(),
  cancelImportAction: vi.fn(),
}));

const save = vi.mocked(saveImportMappingAction);
const cancel = vi.mocked(cancelImportAction);

describe("ColumnMapper", () => {
  beforeEach(() => {
    save.mockReset();
    cancel.mockReset();
  });

  it("starts from the suggested mapping and previews the file", () => {
    render(<ColumnMapper batch={importDetail()} onChange={vi.fn()} />);

    expect(screen.getByLabelText(/Business name/)).toHaveValue("Company");
    expect(screen.getByLabelText("Website")).toHaveValue("Site");
    expect(screen.getByLabelText("City")).toHaveValue("");
    expect(screen.getByRole("cell", { name: "Acme Dental" })).toBeInTheDocument();
  });

  it("restores a saved mapping over the suggestion", () => {
    render(
      <ColumnMapper batch={importDetail({ column_mapping: { business_name: "Site" } })} onChange={vi.fn()} />,
    );
    expect(screen.getByLabelText(/Business name/)).toHaveValue("Site");
  });

  it("submits a manual mapping", async () => {
    const next = importDetail();
    save.mockResolvedValue({ ok: true, data: next });
    const onChange = vi.fn();
    render(<ColumnMapper batch={importDetail()} onChange={onChange} />);

    await userEvent.selectOptions(screen.getByLabelText("City"), "City");
    await userEvent.selectOptions(screen.getByLabelText("Website"), "");
    await userEvent.click(screen.getByRole("button", { name: /Validate 3 rows/ }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(next));
    expect(save).toHaveBeenCalledWith(importDetail().id, { business_name: "Company", city: "City" });
  });

  it("requires a business name column", async () => {
    render(<ColumnMapper batch={importDetail()} onChange={vi.fn()} />);

    await userEvent.selectOptions(screen.getByLabelText(/Business name/), "");

    expect(screen.getByRole("button", { name: /Validate/ })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(/business name/i);
  });

  it("refuses the same column twice", async () => {
    render(<ColumnMapper batch={importDetail()} onChange={vi.fn()} />);

    await userEvent.selectOptions(screen.getByLabelText("City"), "Company");

    expect(screen.getByRole("button", { name: /Validate/ })).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent("Company");
  });

  it("shows server errors", async () => {
    save.mockResolvedValue({ ok: false, message: "Unknown columns: Site." });
    render(<ColumnMapper batch={importDetail()} onChange={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: /Validate/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Unknown columns: Site.");
  });

  it("can discard the import", async () => {
    const cancelled = importDetail({ status: "cancelled" });
    cancel.mockResolvedValue({ ok: true, data: cancelled });
    const onChange = vi.fn();
    render(<ColumnMapper batch={importDetail()} onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /Discard/ }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(cancelled));
  });
});
