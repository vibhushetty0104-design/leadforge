import type { ImportBatchRead } from "@leadforge/shared";
import Link from "next/link";

import { DataTable, type Column } from "@/components/data/data-table";
import { ImportStatusBadge } from "@/components/data/status-badge";
import { formatDateTime, formatNumber } from "@/lib/format";

const COLUMNS: Column<ImportBatchRead>[] = [
  {
    id: "file",
    header: "File",
    cell: (batch) => (
      <Link href={`/discovery/imports/${batch.id}`} className="font-medium hover:text-primary-hover">
        {batch.filename}
      </Link>
    ),
  },
  { id: "status", header: "Status", cell: (batch) => <ImportStatusBadge status={batch.status} /> },
  {
    id: "rows",
    header: "Rows",
    hideBelow: "sm",
    cell: (batch) => <span className="tabular-nums text-muted-foreground">{formatNumber(batch.total_rows)}</span>,
  },
  {
    id: "created",
    header: "Created",
    hideBelow: "md",
    cell: (batch) => <span className="tabular-nums text-muted-foreground">{formatNumber(batch.created_count)}</span>,
  },
  {
    id: "date",
    header: "Uploaded",
    hideBelow: "md",
    cell: (batch) => <span className="whitespace-nowrap text-muted-foreground">{formatDateTime(batch.created_at)}</span>,
  },
];

export function ImportTable({ imports }: { imports: ImportBatchRead[] }) {
  return <DataTable caption="CSV imports" columns={COLUMNS} rows={imports} rowKey={(batch) => batch.id} />;
}
