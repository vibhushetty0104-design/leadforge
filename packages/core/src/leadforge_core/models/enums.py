"""Constrained status and category values used across the domain."""

from enum import StrEnum


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class BusinessStatus(StrEnum):
    NEW = "new"
    RESEARCHING = "researching"
    QUALIFIED = "qualified"
    CONTACTED = "contacted"
    ENGAGED = "engaged"
    WON = "won"
    LOST = "lost"
    DISQUALIFIED = "disqualified"


class RecordSource(StrEnum):
    MANUAL = "manual"
    CSV_IMPORT = "csv_import"
    DEVELOPMENT_SEED = "development_seed"


class AuditStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class FindingCategory(StrEnum):
    PERFORMANCE = "performance"
    SEO = "seo"
    ACCESSIBILITY = "accessibility"
    CONVERSION = "conversion"
    SECURITY = "security"
    CONTENT = "content"
    TECHNICAL = "technical"


class FindingSeverity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class JobType(StrEnum):
    WEBSITE_AUDIT = "website_audit"
    LEAD_SCORING = "lead_scoring"
    IMPORT = "import"
    URL_VALIDATION = "url_validation"
    WEBSITE_INSPECTION = "website_inspection"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CampaignStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class EmailDraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    # LEADFORGE never sends email itself; "sent" is recorded by the user after
    # sending from their own mail client.
    SENT = "sent"
    DISCARDED = "discarded"


class SuppressionReason(StrEnum):
    UNSUBSCRIBED = "unsubscribed"
    BOUNCED = "bounced"
    COMPLAINT = "complaint"
    DO_NOT_CONTACT = "do_not_contact"
    MANUAL = "manual"


class ActivityType(StrEnum):
    NOTE = "note"
    CALL = "call"
    EMAIL_SENT = "email_sent"
    EMAIL_RECEIVED = "email_received"
    MEETING = "meeting"
    STATUS_CHANGE = "status_change"
    FOLLOW_UP = "follow_up"


class WebsiteStatus(StrEnum):
    UNKNOWN = "unknown"
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    # Refused by our safety rules, robots.txt, or the site's own access controls.
    BLOCKED = "blocked"


class ImportStatus(StrEnum):
    DRAFT = "draft"  # uploaded; awaiting column mapping and confirmation
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ImportRowOutcome(StrEnum):
    PENDING = "pending"
    INVALID = "invalid"
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED_DUPLICATE = "skipped_duplicate"
    # A possible match nobody decided on: nothing was written for this row.
    NEEDS_REVIEW = "needs_review"


class DuplicateAction(StrEnum):
    SKIP = "skip"
    UPDATE = "update"  # fills blank fields on the existing record, never overwrites
    CREATE = "create"  # keep as a separate business


class InspectionStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"
