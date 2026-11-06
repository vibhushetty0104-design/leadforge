from __future__ import annotations

import csv
import io
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from leadforge_core.models import (
    AuditLog,
    Business,
    InspectionStatus,
    Job,
    JobType,
    MemberRole,
    Organization,
    RecordSource,
    WebsiteInspection,
    WebsiteStatus,
)

from .conftest import Actor

URL = "/api/v1/businesses"


def _create(client: TestClient, actor: Actor, **fields: Any) -> dict[str, Any]:
    response = client.post(URL, json={"name": "Riverside Dental", **fields}, headers=actor.headers)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_create_preserves_the_submitted_url(client: TestClient, owner: Actor) -> None:
    body = _create(
        client,
        owner,
        website_url=" HTTP://WWW.Riverside.Example.com:80/about/ ",
        email="Hello@Riverside.Example.com",
        description="Family dentist",
        source_url="https://directory.example.org/riverside/",
    )
    assert body["website_url"] == "http://www.riverside.example.com/about"
    assert body["website_url_original"] == "HTTP://WWW.Riverside.Example.com:80/about/"
    assert body["domain"] == "riverside.example.com"
    assert body["email"] == "hello@riverside.example.com"
    assert body["source_url"] == "https://directory.example.org/riverside"
    assert body["website_status"] == "unknown"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email"},
        {"source_url": "http://localhost/admin"},
        {"website_url": "http://[::1]/"},
        {"description": "x" * 5001},
    ],
)
def test_new_fields_are_validated(
    client: TestClient, owner: Actor, payload: dict[str, str]
) -> None:
    response = client.post(URL, json={"name": "X", **payload}, headers=owner.headers)
    assert response.status_code == 422


def test_same_domain_needs_an_explicit_decision(client: TestClient, owner: Actor) -> None:
    first = _create(client, owner, name="Acme Dental", website_url="acme.example.com")
    conflict = client.post(
        URL,
        json={"name": "Zenith Physio", "website_url": "acme.example.com"},
        headers=owner.headers,
    )
    assert conflict.status_code == 409
    details = conflict.json()["error"]["details"]
    assert details["kind"] == "possible"
    assert details["existing_id"] == first["id"]

    second = _create(
        client, owner, name="Zenith Physio", website_url="acme.example.com", allow_duplicate=True
    )
    assert second["id"] != first["id"]
    assert second["domain"] == first["domain"]


def test_name_and_country_duplicates_are_caught(client: TestClient, owner: Actor) -> None:
    _create(client, owner, name="Acme Dental", country_code="GB")
    response = client.post(
        URL, json={"name": "ACME Dental Ltd", "country_code": "gb"}, headers=owner.headers
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["kind"] == "definite"
    _create(client, owner, name="Acme Dental", country_code="AU")  # another country is fine


def test_shared_platform_pages_are_distinct_businesses(client: TestClient, owner: Actor) -> None:
    first = _create(client, owner, name="Bakery", website_url="https://facebook.com/bakery")
    second = _create(client, owner, name="Plumber", website_url="https://facebook.com/plumber")
    assert first["domain"] == second["domain"] == "facebook.com"
    repeat = client.post(
        URL,
        json={"name": "Bakery 2", "website_url": "https://facebook.com/bakery"},
        headers=owner.headers,
    )
    assert repeat.status_code == 409


def test_patch_updates_only_sent_fields_and_is_audited(
    client: TestClient, owner: Actor, db: Session
) -> None:
    business = _create(client, owner, city="Leeds", notes="keep me")
    response = client.patch(
        f"{URL}/{business['id']}",
        json={"status": "qualified", "city": None},
        headers=owner.headers,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "qualified"
    assert body["city"] is None
    assert body["notes"] == "keep me"
    log = db.scalars(select(AuditLog).where(AuditLog.action == "business.updated")).one()
    assert log.details == {"fields": ["city", "status"]}


def test_patch_changing_website_resets_its_status(
    client: TestClient, owner: Actor, db: Session
) -> None:
    created = _create(client, owner, website_url="old.example.com")
    record = db.get(Business, uuid.UUID(created["id"]))
    assert record is not None
    record.website_status = WebsiteStatus.REACHABLE
    db.commit()

    body = client.patch(
        f"{URL}/{created['id']}", json={"website_url": "new.example.com"}, headers=owner.headers
    ).json()
    assert body["domain"] == "new.example.com"
    assert body["website_status"] == "unknown"

    same = client.patch(
        f"{URL}/{created['id']}", json={"website_url": "new.example.com"}, headers=owner.headers
    )
    assert same.status_code == 200


def test_patch_detects_duplicates_but_ignores_itself(client: TestClient, owner: Actor) -> None:
    first = _create(client, owner, name="Acme", website_url="acme.example.com")
    second = _create(client, owner, name="Zenith", website_url="zenith.example.com")

    assert (
        client.patch(
            f"{URL}/{first['id']}", json={"name": "Acme Dental"}, headers=owner.headers
        ).status_code
        == 200
    )
    conflict = client.patch(
        f"{URL}/{second['id']}", json={"website_url": "acme.example.com"}, headers=owner.headers
    )
    assert conflict.status_code == 409
    resolved = client.patch(
        f"{URL}/{second['id']}",
        json={"website_url": "acme.example.com", "allow_duplicate": True},
        headers=owner.headers,
    )
    assert resolved.status_code == 200


@pytest.mark.parametrize(
    "payload",
    [
        {"name": None},
        {"status": None},
        {"organization_id": str(uuid.uuid4())},
        {"source": "manual"},
    ],
)
def test_patch_rejects_bad_fields(
    client: TestClient, owner: Actor, payload: dict[str, Any]
) -> None:
    business = _create(client, owner)
    assert (
        client.patch(f"{URL}/{business['id']}", json=payload, headers=owner.headers).status_code
        == 422
    )


def test_patch_is_org_scoped(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    business = _create(client, owner)
    intruder = make_actor()
    assert (
        client.patch(
            f"{URL}/{business['id']}", json={"city": "x"}, headers=intruder.headers
        ).status_code
        == 404
    )


def _seed_directory(db: Session, actor: Actor) -> None:
    org = actor.organization_id
    db.add_all(
        [
            Business(
                organization_id=org,
                name="Acme Dental",
                domain="acme.com",
                website_url="https://acme.com/",
                industry="Dental clinic",
                country_code="GB",
                email="hi@acme.com",
                website_status=WebsiteStatus.REACHABLE,
                source=RecordSource.CSV_IMPORT,
            ),
            Business(
                organization_id=org,
                name="Beta Plumbing",
                industry="Plumbing",
                country_code="US",
                website_status=WebsiteStatus.UNKNOWN,
            ),
        ]
    )
    db.commit()


@pytest.mark.parametrize(
    ("params", "names"),
    [
        ({"industry": "dental"}, ["Acme Dental"]),
        ({"country_code": "us"}, ["Beta Plumbing"]),
        ({"website_status": "reachable"}, ["Acme Dental"]),
        ({"source": "csv_import"}, ["Acme Dental"]),
        ({"has_email": "true"}, ["Acme Dental"]),
        ({"has_email": "false"}, ["Beta Plumbing"]),
        ({"has_website": "false"}, ["Beta Plumbing"]),
        ({"q": "acme", "country_code": "US"}, []),
    ],
)
def test_directory_filters(
    client: TestClient, owner: Actor, db: Session, params: dict[str, str], names: list[str]
) -> None:
    _seed_directory(db, owner)
    body = client.get(URL, params=params, headers=owner.headers).json()
    assert [item["name"] for item in body["items"]] == names


def _export(client: TestClient, actor: Actor, body: dict[str, Any]) -> list[dict[str, str]]:
    response = client.post(f"{URL}/export", json=body, headers=actor.headers)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    return list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))


def test_export_honours_filters(client: TestClient, owner: Actor, db: Session) -> None:
    _seed_directory(db, owner)
    rows = _export(client, owner, {"country_code": "GB"})
    assert [row["name"] for row in rows] == ["Acme Dental"]
    assert rows[0]["email"] == "hi@acme.com"


def test_export_selected_ids_only(client: TestClient, owner: Actor) -> None:
    first = _create(client, owner, name="One")
    _create(client, owner, name="Two")
    rows = _export(client, owner, {"business_ids": [first["id"]]})
    assert [row["name"] for row in rows] == ["One"]


def test_export_neutralises_spreadsheet_formulas(
    client: TestClient, owner: Actor, db: Session
) -> None:
    db.add(Business(organization_id=owner.organization_id, name='=HYPERLINK("http://evil")'))
    db.commit()
    assert _export(client, owner, {})[0]["name"].startswith("'=")


def test_export_is_org_scoped_and_audited(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    secret = _create(client, owner, name="Secret")
    intruder = make_actor()
    assert _export(client, intruder, {"business_ids": [secret["id"]]}) == []
    assert db.scalars(select(AuditLog).where(AuditLog.action == "business.exported")).first()


def test_inspect_queues_one_job(client: TestClient, owner: Actor, db: Session) -> None:
    business = _create(client, owner, website_url="acme.example.com")
    first = client.post(f"{URL}/{business['id']}/inspect", headers=owner.headers)
    assert first.status_code == 202
    second = client.post(f"{URL}/{business['id']}/inspect", headers=owner.headers)
    assert second.json()["id"] == first.json()["id"]
    assert len(db.scalars(select(Job).where(Job.type == JobType.WEBSITE_INSPECTION)).all()) == 1

    state = client.get(f"{URL}/{business['id']}/inspection", headers=owner.headers).json()
    assert state["inspection"] is None
    assert state["active_job"]["id"] == first.json()["id"]


def test_inspect_requires_a_website(client: TestClient, owner: Actor) -> None:
    business = _create(client, owner)
    response = client.post(f"{URL}/{business['id']}/inspect", headers=owner.headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "business_has_no_website"


def test_inspection_returns_latest_result(client: TestClient, owner: Actor, db: Session) -> None:
    business = _create(client, owner, website_url="acme.example.com")
    db.add(
        WebsiteInspection(
            organization_id=owner.organization_id,
            business_id=uuid.UUID(business["id"]),
            status=InspectionStatus.SUCCESS,
            requested_url="https://acme.example.com/",
            domain="acme.example.com",
            title="Acme",
            emails=["hi@acme.example.com"],
        )
    )
    db.commit()
    body = client.get(f"{URL}/{business['id']}/inspection", headers=owner.headers).json()
    assert body["inspection"]["title"] == "Acme"
    assert body["inspection"]["emails"] == ["hi@acme.example.com"]
    assert body["active_job"] is None


def test_bulk_inspect_reports_each_outcome(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    site = _create(client, owner, name="Site", website_url="site.example.com")
    busy = _create(client, owner, name="Busy", website_url="busy.example.com")
    none = _create(client, owner, name="No site")
    foreign = _create(client, make_actor(), name="Foreign", website_url="foreign.example.com")
    client.post(f"{URL}/{busy['id']}/inspect", headers=owner.headers)

    response = client.post(
        f"{URL}/bulk-inspect",
        json={"business_ids": [site["id"], busy["id"], none["id"], foreign["id"], site["id"]]},
        headers=owner.headers,
    )
    assert response.status_code == 202
    body = response.json()
    assert body["queued"] == 1
    assert body["already_active"] == 1
    assert body["skipped_no_website"] == 1
    assert body["not_found"] == 1


def test_bulk_inspect_is_bounded(client: TestClient, owner: Actor) -> None:
    ids = [str(uuid.uuid4()) for _ in range(101)]
    assert (
        client.post(
            f"{URL}/bulk-inspect", json={"business_ids": ids}, headers=owner.headers
        ).status_code
        == 422
    )


def test_job_status_is_org_scoped(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    business = _create(client, owner, website_url="acme.example.com")
    job = client.post(f"{URL}/{business['id']}/inspect", headers=owner.headers).json()

    body = client.get(f"/api/v1/jobs/{job['id']}", headers=owner.headers).json()
    assert body["status"] == "queued"
    assert body["progress_current"] == 0
    assert client.get(f"/api/v1/jobs/{job['id']}", headers=make_actor().headers).status_code == 404


def test_discovery_summary_counts_real_data(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    _seed_directory(db, owner)
    _seed_directory(db, make_actor())
    body = client.get("/api/v1/discovery/summary", headers=owner.headers).json()
    assert body["total_businesses"] == 2
    assert body["with_website"] == 1
    assert body["with_email"] == 1
    assert body["by_website_status"]["reachable"] == 1
    assert body["recent_imports"] == []


def test_member_can_edit_but_not_delete(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    business = _create(client, owner)
    org = db.get(Organization, owner.organization_id)
    member = make_actor(MemberRole.MEMBER, organization=org)
    assert (
        client.patch(
            f"{URL}/{business['id']}", json={"city": "York"}, headers=member.headers
        ).status_code
        == 200
    )
    assert client.delete(f"{URL}/{business['id']}", headers=member.headers).status_code == 403
