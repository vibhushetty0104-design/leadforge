import type {
  BusinessStatus,
  ImportRowOutcome,
  ImportStatus,
  InspectionRead,
  WebsiteStatus,
} from "@leadforge/shared";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { humanize } from "@/lib/format";

const TONES: Record<BusinessStatus, BadgeTone> = {
  new: "neutral",
  researching: "blue",
  qualified: "violet",
  contacted: "blue",
  engaged: "teal",
  won: "teal",
  lost: "red",
  disqualified: "neutral",
};

export function BusinessStatusBadge({ status }: { status: BusinessStatus }) {
  return <Badge tone={TONES[status]}>{humanize(status)}</Badge>;
}

const WEBSITE_TONES: Record<WebsiteStatus, BadgeTone> = {
  unknown: "neutral",
  reachable: "teal",
  unreachable: "red",
  blocked: "amber",
};

const WEBSITE_LABELS: Record<WebsiteStatus, string> = {
  unknown: "Not checked",
  reachable: "Reachable",
  unreachable: "Unreachable",
  blocked: "Blocked",
};

export function WebsiteStatusBadge({ status }: { status: WebsiteStatus }) {
  return <Badge tone={WEBSITE_TONES[status]}>{WEBSITE_LABELS[status]}</Badge>;
}

const IMPORT_TONES: Record<ImportStatus, BadgeTone> = {
  draft: "neutral",
  queued: "blue",
  running: "blue",
  completed: "teal",
  failed: "red",
  cancelled: "neutral",
};

export function ImportStatusBadge({ status }: { status: ImportStatus }) {
  return <Badge tone={IMPORT_TONES[status]}>{status === "draft" ? "Needs review" : humanize(status)}</Badge>;
}

const OUTCOME_TONES: Record<ImportRowOutcome, BadgeTone> = {
  pending: "neutral",
  invalid: "red",
  created: "teal",
  updated: "blue",
  skipped_duplicate: "neutral",
  needs_review: "amber",
};

const OUTCOME_LABELS: Record<ImportRowOutcome, string> = {
  pending: "Pending",
  invalid: "Rejected",
  created: "Created",
  updated: "Updated",
  skipped_duplicate: "Skipped",
  needs_review: "Not imported",
};

export function RowOutcomeBadge({ outcome }: { outcome: ImportRowOutcome }) {
  return <Badge tone={OUTCOME_TONES[outcome]}>{OUTCOME_LABELS[outcome]}</Badge>;
}

const INSPECTION_TONES: Record<InspectionRead["status"], BadgeTone> = {
  success: "teal",
  failed: "red",
  blocked: "amber",
};

export function InspectionStatusBadge({ status }: { status: InspectionRead["status"] }) {
  return <Badge tone={INSPECTION_TONES[status]}>{humanize(status)}</Badge>;
}
