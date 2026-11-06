"use client";

import type { ImportDetail } from "@leadforge/shared";
import { Ban } from "lucide-react";
import { useState } from "react";

import { PageHeader } from "@/components/data/page-header";
import { EmptyState } from "@/components/data/states";
import { ImportStatusBadge } from "@/components/data/status-badge";
import { ColumnMapper } from "@/components/discovery/column-mapper";
import { ImportProgress } from "@/components/discovery/import-progress";
import { ImportResults } from "@/components/discovery/import-results";
import { ImportReview } from "@/components/discovery/import-review";

/** Shows the step matching the import's current state, so any step can be resumed. */
export function ImportWorkspace({ initial, canUpdate }: { initial: ImportDetail; canUpdate: boolean }) {
  const [batch, setBatch] = useState(initial);
  const [editingMapping, setEditingMapping] = useState(false);

  function change(next: ImportDetail) {
    setEditingMapping(false);
    setBatch(next);
  }

  return (
    <>
      <PageHeader title={batch.filename} actions={<ImportStatusBadge status={batch.status} />} />
      {step()}
    </>
  );

  function step() {
    if (batch.status === "cancelled") {
      return <EmptyState icon={Ban} title="Import discarded" description="No records were created from this file." />;
    }
    if (batch.status === "queued" || batch.status === "running") {
      return <ImportProgress batch={batch} onChange={setBatch} />;
    }
    if (batch.status === "draft") {
      if (batch.preview && !editingMapping) {
        return (
          <ImportReview
            batch={batch}
            canUpdate={canUpdate}
            onChange={change}
            onEditMapping={() => setEditingMapping(true)}
          />
        );
      }
      return <ColumnMapper batch={batch} onChange={change} />;
    }
    return <ImportResults batch={batch} />;
  }
}
