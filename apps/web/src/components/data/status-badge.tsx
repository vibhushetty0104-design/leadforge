import type { BusinessStatus } from "@leadforge/shared";

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
