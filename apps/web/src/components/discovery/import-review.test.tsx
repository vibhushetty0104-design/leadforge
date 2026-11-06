import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { confirmImportAction, listImportRowsAction, resolveImportRowAction } from "@/app/actions";
import { ImportResults } from "@/components/discovery/import-results";
import { ImportReview } from "@/components/discovery/import-review";
import { importDetail, importRow } from "@/components/discovery/test-fixtures";

vi.mock("@/app/actions", () => ({
  confirmImportAction: vi.fn(),
  cancelImportAction: vi.fn(),
  listImportRowsAction: vi.fn(),
  resolveImportRowAction: vi.fn(),
}));

const list = vi.mocked(listImportRowsAction);
const resolve = vi.mocked(resolveImportRowAction);
const confirm = vi.mocked(confirmImportAction);

const preview = {
  total: 4,
  valid: 3,
  invalid: 1,
  with_warnings: 0,
  definite_duplicates: 1,
  possible_duplicates: 1,
  resolved: 0,
};
const batch = importDetail({ preview, column_mapping: { business_name: "Company" } });

const definite = importRow({
  id: "d",
  row_number: 2,
  normalized: { name: "Acme Dental" },
  duplicate: { kind: "definite", reason: "Same website and business name", name: "Acme", domain: "acme.com", business_id: "b", row_number: null },
});
const possible = importRow({
  id: "p",
  row_number: 3,
  normalized: { name: "Zenith Physio" },
  duplicate: { kind: "possible", reason: "Same website but a different business name", name: "Acme", domain: "acme.com", business_id: "b", row_number: null },
});
const rejected = importRow({
  id: "x",
  row_number: 4,
  normalized: { name: "Broken" },
  outcome: "invalid",
  errors: ["Website: only http and https URLs are allowed."],
});

function page(items: ReturnType<typeof importRow>[]) {
  return { ok: true as const, data: { items, total: items.length, limit: 25, offset: 0 } };
}

function renderReview(canUpdate = true, onChange = vi.fn()) {
  render(<ImportReview batch={batch} canUpdate={canUpdate} onChange={onChange} onEditMapping={vi.fn()} />);
  return onChange;
}

describe("ImportReview", () => {
  beforeEach(() => {
    list.mockReset();
    resolve.mockReset();
    confirm.mockReset();
    list.mockImplementation(async (_id, options) =>
      page(options.duplicatesOnly ? [definite, possible] : [rejected]),
    );
  });

  it("summarises validation and explains rejected rows", async () => {
    renderReview();

    expect(await screen.findByText(/Row 4: Broken/)).toBeInTheDocument();
    expect(screen.getByText("Website: only http and https URLs are allowed.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Start import" })).toBeEnabled();
  });

  it("distinguishes definite from possible duplicates", async () => {
    renderReview();

    expect(await screen.findByText("Duplicate")).toBeInTheDocument();
    expect(screen.getByText("Possible duplicate")).toBeInTheDocument();
    expect(screen.getByText(/different business name/)).toBeInTheDocument();
  });

  it("saves a decision for one row", async () => {
    resolve.mockResolvedValue({ ok: true, data: possible });
    renderReview();

    const select = await screen.findByLabelText("Decision for Zenith Physio");
    await userEvent.selectOptions(select, "create");

    await waitFor(() => expect(resolve).toHaveBeenCalledWith(batch.id, "p", "create"));
  });

  it("reverts a decision the server refuses and says why", async () => {
    resolve.mockResolvedValue({ ok: false, message: "Your role does not permit this action." });
    renderReview();

    const select = await screen.findByLabelText("Decision for Zenith Physio");
    await userEvent.selectOptions(select, "create");

    expect(await screen.findByRole("alert")).toHaveTextContent("does not permit");
    expect(select).toHaveValue("");
  });

  it("hides overwriting choices from members", async () => {
    renderReview(false);

    await screen.findByLabelText("Decision for Acme Dental");
    expect(screen.queryByRole("option", { name: "Fill in blanks" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Fill in blanks/)).not.toBeInTheDocument();
  });

  it("confirms with the chosen policy", async () => {
    const queued = importDetail({ status: "queued" });
    confirm.mockResolvedValue({ ok: true, data: queued });
    const onChange = renderReview();

    await screen.findByText("Duplicate");
    await userEvent.click(screen.getByLabelText(/Fill in blanks/));
    await userEvent.click(screen.getByLabelText(/Check websites after importing/));
    await userEvent.click(screen.getByRole("button", { name: "Start import" }));

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(queued));
    expect(confirm).toHaveBeenCalledWith(batch.id, { duplicatePolicy: "update", validateWebsites: false });
  });

  it("will not import when no rows are valid", async () => {
    list.mockResolvedValue(page([]));
    render(
      <ImportReview
        batch={{ ...batch, preview: { ...preview, valid: 0 } }}
        canUpdate
        onChange={vi.fn()}
        onEditMapping={vi.fn()}
      />,
    );
    expect(await screen.findByRole("button", { name: "Start import" })).toBeDisabled();
  });
});

describe("ImportResults", () => {
  beforeEach(() => {
    list.mockReset();
  });

  const finished = importDetail({
    status: "completed",
    created_count: 2,
    skipped_count: 1,
    invalid_count: 1,
    review_count: 1,
  });

  it("gives a warning summary and row-level detail", async () => {
    list.mockResolvedValue(page([{ ...rejected }]));
    render(<ImportResults batch={finished} />);

    expect(screen.getByRole("status")).toHaveTextContent("2 rows not imported");
    expect(await screen.findByText(rejected.errors[0]!)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "View imported businesses" })).toHaveAttribute(
      "href",
      `/leads?import_id=${finished.id}`,
    );
  });

  it("reports success when nothing went wrong", async () => {
    list.mockResolvedValue(page([]));
    render(<ImportResults batch={importDetail({ status: "completed", created_count: 3 })} />);

    expect(await screen.findByRole("status")).toHaveTextContent(/processed successfully/);
  });

  it("shows why an import failed", async () => {
    list.mockResolvedValue(page([]));
    render(<ImportResults batch={importDetail({ status: "failed", error_message: "Saved rows were kept." })} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Saved rows were kept.");
  });

  it("filters rows by outcome", async () => {
    list.mockResolvedValue(page([]));
    render(<ImportResults batch={finished} />);

    await userEvent.click(screen.getByRole("button", { name: "Rejected" }));

    await waitFor(() => expect(list).toHaveBeenCalledWith(finished.id, { outcome: "invalid", offset: 0 }));
  });
});
