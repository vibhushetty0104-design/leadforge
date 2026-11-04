from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from leadforge_core import queue
from leadforge_core.models import (
    Activity,
    ActivityType,
    Business,
    BusinessStatus,
    JobType,
    LeadScore,
)
from leadforge_core.models.base import utcnow

from .conftest import Actor, make_token


def test_health_reports_database(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "ok"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Request-ID"]


def test_request_id_is_propagated(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "trace-abc-12345"})
    assert response.headers["X-Request-ID"] == "trace-abc-12345"
    # Unsafe values are replaced rather than reflected.
    response = client.get("/health", headers={"X-Request-ID": "bad id\n"})
    assert response.headers["X-Request-ID"] != "bad id\n"


def test_cors_allows_only_configured_origins(client: TestClient) -> None:
    preflight = {
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,x-organization-id",
    }
    ok = client.options("/api/v1/me", headers={"Origin": "http://localhost:3000", **preflight})
    assert ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    denied = client.options("/api/v1/me", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in denied.headers


def test_unknown_route_uses_structured_error(client: TestClient) -> None:
    body = client.get("/api/v1/nope").json()
    assert body["error"]["code"] == "not_found"


def test_dashboard_empty_org_reports_zeros(client: TestClient, owner: Actor) -> None:
    body = client.get("/api/v1/dashboard/summary", headers=owner.headers).json()
    assert body["businesses"]["total"] == 0
    assert body["scores"]["average_latest_score"] is None
    assert body["organization"]["is_development_seed"] is False
    assert set(body["jobs"]) == {"queued", "running", "completed", "failed"}


def test_dashboard_aggregates_only_own_org(
    client: TestClient,
    owner: Actor,
    make_actor,
    db: Session,  # type: ignore[no-untyped-def]
) -> None:
    org_id = owner.organization_id
    a = Business(
        organization_id=org_id,
        name="A",
        status=BusinessStatus.QUALIFIED,
        created_at=utcnow() - timedelta(hours=1),
    )
    b = Business(organization_id=org_id, name="B", created_at=utcnow())
    db.add_all([a, b])
    db.flush()
    # Only the latest score per business counts: A -> 80 (not 20), B -> 60.
    db.add_all(
        [
            LeadScore(
                organization_id=org_id,
                business_id=a.id,
                score=20,
                model_version="v1",
                computed_at=utcnow() - timedelta(days=2),
            ),
            LeadScore(organization_id=org_id, business_id=a.id, score=80, model_version="v1"),
            LeadScore(organization_id=org_id, business_id=b.id, score=60, model_version="v1"),
            Activity(
                organization_id=org_id,
                business_id=a.id,
                type=ActivityType.FOLLOW_UP,
                summary="Call back",
                due_at=utcnow() - timedelta(days=1),
            ),
            Activity(
                organization_id=org_id,
                business_id=b.id,
                type=ActivityType.FOLLOW_UP,
                summary="Send audit",
                due_at=utcnow() + timedelta(days=1),
            ),
        ]
    )
    queue.enqueue(db, organization_id=org_id, job_type=JobType.WEBSITE_AUDIT)
    other = make_actor()
    db.add(Business(organization_id=other.organization_id, name="Foreign"))
    db.commit()

    body = client.get("/api/v1/dashboard/summary", headers=owner.headers).json()
    assert body["businesses"]["total"] == 2
    assert body["businesses"]["added_last_30_days"] == 2
    assert body["businesses"]["by_status"]["qualified"] == 1
    assert body["scores"] == {"scored_businesses": 2, "average_latest_score": 70.0}
    assert body["follow_ups"] == {"open": 2, "overdue": 1}
    assert body["jobs"]["queued"] == 1
    assert [r["name"] for r in body["recent_businesses"]] == ["B", "A"]


def test_create_organization_makes_caller_owner(client: TestClient) -> None:
    import uuid

    user_id = uuid.uuid4()
    auth = {"Authorization": f"Bearer {make_token(user_id)}"}
    response = client.post("/api/v1/organizations", json={"name": "Northwind Studio"}, headers=auth)
    assert response.status_code == 201
    membership = response.json()
    assert membership["role"] == "owner"
    assert membership["organization"]["slug"].startswith("northwind-studio-")

    me = client.get("/api/v1/me", headers=auth).json()
    assert [m["organization"]["id"] for m in me["memberships"]] == [
        membership["organization"]["id"]
    ]

    headers = {**auth, "X-Organization-Id": membership["organization"]["id"]}
    assert client.get("/api/v1/dashboard/summary", headers=headers).status_code == 200


def test_docs_disabled_in_production(settings) -> None:  # type: ignore[no-untyped-def]
    from leadforge_api.main import create_app

    prod = settings.model_copy(update={"environment": "production"})
    app_client = TestClient(create_app(prod))
    assert app_client.get("/docs").status_code == 404
    assert app_client.get("/openapi.json").status_code == 404
