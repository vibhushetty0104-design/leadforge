from __future__ import annotations

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
    ImportRow,
    Job,
    JobStatus,
    JobType,
    MemberRole,
    Organization,
)

from .conftest import Actor

URL = "/api/v1/imports"
CSV = (
    b"Company,Website,Email,Country,Town\n"
    b"Acme Dental,acme.com,hello@acme.com,GB,Leeds\n"
    b"Beta Plumbing,beta.co.uk,,UK,York\n"
    b",nameless.com,,,\n"
    b"Gamma Gyms,not a url,,GB,\n"
    b"Delta Decor,delta.com,bad-email,GB,\n"
)
MAPPING = {
    "business_name": "Company",
    "website": "Website",
    "email": "Email",
    "country": "Country",
    "city": "Town",
}


def _upload(client: TestClient, actor: Actor, content: bytes = CSV, name: str = "leads.csv") -> Any:
    return client.post(
        f"{URL}/csv",
        params={"filename": name},
        content=content,
        headers={**actor.headers, "Content-Type": "text/csv"},
    )


def _uploaded(client: TestClient, actor: Actor, content: bytes = CSV) -> dict[str, Any]:
    response = _upload(client, actor, content)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _mapped(
    client: TestClient,
    actor: Actor,
    content: bytes = CSV,
    mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    batch = _uploaded(client, actor, content)
    response = client.post(
        f"{URL}/{batch['id']}/mapping",
        json={"column_mapping": mapping or batch["suggested_mapping"]},
        headers=actor.headers,
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def test_upload_stores_rows_and_suggests_a_mapping(
    client: TestClient, owner: Actor, db: Session
) -> None:
    body = _uploaded(client, owner)
    assert body["status"] == "draft"
    assert body["total_rows"] == 5
    assert body["headers"] == ["Company", "Website", "Email", "Country", "Town"]
    assert body["suggested_mapping"] == MAPPING
    assert body["sample_rows"][0]["Company"] == "Acme Dental"
    assert body["preview"] is None
    assert len(db.scalars(select(ImportRow)).all()) == 5
    assert db.scalars(select(Business)).all() == []  # nothing is saved before confirmation


@pytest.mark.parametrize(
    ("name", "status", "code"),
    [("leads.txt", 422, "import_invalid_file"), ("leads.xlsx", 422, "import_invalid_file")],
)
def test_rejects_other_file_types(
    client: TestClient, owner: Actor, name: str, status: int, code: str
) -> None:
    response = _upload(client, owner, name=name)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_rejects_unsupported_content_type(client: TestClient, owner: Actor) -> None:
    response = client.post(
        f"{URL}/csv",
        params={"filename": "a.csv"},
        content=CSV,
        headers={**owner.headers, "Content-Type": "application/json"},
    )
    assert response.status_code == 415


def test_filename_paths_are_stripped(client: TestClient, owner: Actor) -> None:
    response = _upload(client, owner, name="..\\..\\secret\\leads.csv")
    assert response.json()["filename"] == "leads.csv"


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"", "empty"),
        (b"name,city\n", "no data rows"),
        (b"\x00\x01\x02\x03", "binary"),
        (b'name,city\nAcme,Leeds\n"broken,York\n', "malformed"),
    ],
)
def test_malformed_files_are_rejected_clearly(
    client: TestClient, owner: Actor, db: Session, content: bytes, message: str
) -> None:
    response = _upload(client, owner, content)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "import_invalid_csv"
    assert message in response.json()["error"]["message"]
    assert db.scalars(select(ImportRow)).all() == []


def test_upload_size_limit_is_enforced(client: TestClient, owner: Actor) -> None:
    client.app.state.settings.import_max_upload_bytes = 100  # type: ignore[attr-defined]
    response = _upload(client, owner, b"name\n" + b"x" * 200 + b"\n")
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "import_too_large"


def test_upload_limit_does_not_trust_content_length(client: TestClient, owner: Actor) -> None:
    client.app.state.settings.import_max_upload_bytes = 100  # type: ignore[attr-defined]

    def body() -> Any:  # chunked, so no Content-Length header exists
        yield b"name\n"
        yield b"x" * 200

    response = client.post(
        f"{URL}/csv",
        params={"filename": "a.csv"},
        content=body(),
        headers={**owner.headers, "Content-Type": "text/csv"},
    )
    assert response.status_code == 413


def test_row_limit_is_enforced(client: TestClient, owner: Actor, db: Session) -> None:
    client.app.state.settings.import_max_rows = 3  # type: ignore[attr-defined]
    response = _upload(client, owner)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "import_too_many_rows"
    assert db.scalars(select(ImportRow)).all() == []


def test_mapping_validates_every_row(client: TestClient, owner: Actor) -> None:
    preview = _mapped(client, owner)["preview"]
    assert preview["total"] == 5
    assert preview["invalid"] == 3
    assert preview["valid"] == 2


def test_results_explain_rejected_rows(client: TestClient, owner: Actor) -> None:
    batch = _mapped(client, owner)
    rows = client.get(
        f"{URL}/{batch['id']}/results", params={"outcome": "invalid"}, headers=owner.headers
    ).json()
    assert rows["total"] == 3
    errors = {row["row_number"]: " ".join(row["errors"]) for row in rows["items"]}
    assert "Business name is required" in errors[4]
    assert "Website" in errors[5]
    assert "Email" in errors[6]


def test_manual_mapping_replaces_suggestions(client: TestClient, owner: Actor) -> None:
    batch = _mapped(
        client,
        owner,
        b"col_a,col_b\nAcme,acme.com\n",
        {"business_name": "col_b", "website": "col_a"},
    )
    row = client.get(f"{URL}/{batch['id']}/results", headers=owner.headers).json()["items"][0]
    assert row["errors"][0].startswith("Website")  # "Acme" is not a valid hostname


@pytest.mark.parametrize(
    ("mapping", "message"),
    [
        ({"website": "Website"}, "business name"),
        ({"business_name": "Nope"}, "Unknown columns"),
        ({"business_name": "Company", "website": "Company"}, "once"),
    ],
)
def test_bad_mappings_are_rejected(
    client: TestClient, owner: Actor, mapping: dict[str, str], message: str
) -> None:
    batch = _uploaded(client, owner)
    response = client.post(
        f"{URL}/{batch['id']}/mapping", json={"column_mapping": mapping}, headers=owner.headers
    )
    assert response.status_code == 422
    assert message in response.json()["error"]["message"]


def test_unknown_mapping_field_is_rejected(client: TestClient, owner: Actor) -> None:
    batch = _uploaded(client, owner)
    response = client.post(
        f"{URL}/{batch['id']}/mapping",
        json={"column_mapping": {"business_name": "Company", "organization_id": "Website"}},
        headers=owner.headers,
    )
    assert response.status_code == 422


def _existing(db: Session, actor: Actor, name: str, domain: str | None = None) -> Business:
    business = Business(
        organization_id=actor.organization_id, name=name, domain=domain, country_code="GB"
    )
    db.add(business)
    db.commit()
    return business


def test_duplicates_are_detected_against_data_and_within_the_file(
    client: TestClient, owner: Actor, db: Session
) -> None:
    _existing(db, owner, "Acme Dental", "acme.com")
    _existing(db, owner, "Beta Holdings", "beta.co.uk")
    content = (
        b"Company,Website,Email,Country,Town\n"
        b"Acme Dental Ltd,https://www.acme.com/,,GB,\n"  # definite: name and domain
        b"Beta Plumbing,beta.co.uk,,GB,\n"  # possible: domain only
        b"New Co,new.com,,GB,\n"
        b"New Co,new.com,,GB,\n"  # definite: earlier row in this file
    )
    batch = _mapped(client, owner, content)
    assert batch["preview"]["definite_duplicates"] == 2
    assert batch["preview"]["possible_duplicates"] == 1

    rows = client.get(
        f"{URL}/{batch['id']}/results", params={"duplicates_only": True}, headers=owner.headers
    ).json()
    assert rows["total"] == 3
    by_number = {row["row_number"]: row["duplicate"] for row in rows["items"]}
    assert by_number[2]["kind"] == "definite"
    assert by_number[2]["business_id"]
    assert by_number[3]["kind"] == "possible"
    assert by_number[5]["row_number"] == 4


def test_row_decisions_are_saved(client: TestClient, owner: Actor, db: Session) -> None:
    _existing(db, owner, "Acme Dental", "acme.com")
    batch = _mapped(client, owner, b"Company,Website\nAcme Dental,acme.com\nNew,new.com\n")
    rows = client.get(f"{URL}/{batch['id']}/results", headers=owner.headers).json()["items"]
    duplicate, plain = rows

    response = client.patch(
        f"{URL}/{batch['id']}/rows/{duplicate['id']}",
        json={"resolution": "create"},
        headers=owner.headers,
    )
    assert response.status_code == 200
    assert response.json()["resolution"] == "create"

    conflict = client.patch(
        f"{URL}/{batch['id']}/rows/{plain['id']}",
        json={"resolution": "skip"},
        headers=owner.headers,
    )
    assert conflict.status_code == 409


def test_members_cannot_overwrite_existing_records(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    _existing(db, owner, "Acme Dental", "acme.com")
    org = db.get(Organization, owner.organization_id)
    member = make_actor(MemberRole.MEMBER, organization=org)
    batch = _mapped(client, member, b"Company,Website\nAcme Dental,acme.com\n")
    row = client.get(f"{URL}/{batch['id']}/results", headers=member.headers).json()["items"][0]

    update = client.patch(
        f"{URL}/{batch['id']}/rows/{row['id']}",
        json={"resolution": "update"},
        headers=member.headers,
    )
    assert update.status_code == 403
    confirm = client.post(
        f"{URL}/{batch['id']}/confirm",
        json={"duplicate_policy": "update"},
        headers=member.headers,
    )
    assert confirm.status_code == 403
    assert (
        client.post(
            f"{URL}/{batch['id']}/confirm",
            json={"duplicate_policy": "skip"},
            headers=member.headers,
        ).status_code
        == 202
    )


def test_confirm_requires_mapping(client: TestClient, owner: Actor) -> None:
    batch = _uploaded(client, owner)
    response = client.post(f"{URL}/{batch['id']}/confirm", json={}, headers=owner.headers)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "import_not_mapped"


def test_confirm_queues_one_job_and_locks_the_batch(
    client: TestClient, owner: Actor, db: Session
) -> None:
    batch = _mapped(client, owner)
    response = client.post(f"{URL}/{batch['id']}/confirm", json={}, headers=owner.headers)
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"
    assert body["job"]["status"] == "queued"
    assert body["job"]["type"] == "import"

    jobs = db.scalars(select(Job).where(Job.type == JobType.IMPORT)).all()
    assert len(jobs) == 1
    assert jobs[0].dedupe_key == f"import:{batch['id']}"

    again = client.post(f"{URL}/{batch['id']}/confirm", json={}, headers=owner.headers)
    assert again.status_code == 409
    remap = client.post(
        f"{URL}/{batch['id']}/mapping", json={"column_mapping": MAPPING}, headers=owner.headers
    )
    assert remap.status_code == 409


def test_failed_job_surfaces_on_the_import(client: TestClient, owner: Actor, db: Session) -> None:
    batch = _mapped(client, owner)
    client.post(f"{URL}/{batch['id']}/confirm", json={}, headers=owner.headers)
    db.expire_all()
    job = db.scalars(select(Job)).one()
    job.status = JobStatus.FAILED
    db.commit()

    body = client.get(f"{URL}/{batch['id']}", headers=owner.headers).json()
    assert body["status"] == "failed"
    assert body["error_message"]


def test_cancel_discards_row_data(client: TestClient, owner: Actor, db: Session) -> None:
    batch = _mapped(client, owner)
    response = client.post(f"{URL}/{batch['id']}/cancel", headers=owner.headers)
    assert response.json()["status"] == "cancelled"
    db.expire_all()
    assert all(row.raw_data == {} for row in db.scalars(select(ImportRow)))
    assert (
        client.post(f"{URL}/{batch['id']}/confirm", json={}, headers=owner.headers).status_code
        == 409
    )


def test_history_is_paginated_newest_first(client: TestClient, owner: Actor) -> None:
    for _ in range(3):
        _uploaded(client, owner)
    page = client.get(URL, params={"limit": 2}, headers=owner.headers).json()
    assert page["total"] == 3
    assert len(page["items"]) == 2


def test_imports_are_isolated_between_organizations(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    batch = _mapped(client, owner)
    intruder = make_actor()
    import_url = f"{URL}/{batch['id']}"
    assert client.get(import_url, headers=intruder.headers).status_code == 404
    assert client.get(f"{import_url}/results", headers=intruder.headers).status_code == 404
    assert (
        client.post(f"{import_url}/confirm", json={}, headers=intruder.headers).status_code == 404
    )
    assert client.post(f"{import_url}/cancel", headers=intruder.headers).status_code == 404
    assert client.get(URL, headers=intruder.headers).json()["total"] == 0

    row = client.get(f"{import_url}/results", headers=owner.headers).json()["items"][0]
    assert (
        client.patch(
            f"{import_url}/rows/{row['id']}", json={"resolution": "skip"}, headers=intruder.headers
        ).status_code
        == 404
    )


def test_duplicate_detection_ignores_other_organizations(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    other = make_actor()
    _existing(db, other, "Acme Dental", "acme.com")
    batch = _mapped(client, owner, b"Company,Website\nAcme Dental,acme.com\n")
    assert batch["preview"]["definite_duplicates"] == 0


def test_upload_requires_authentication(client: TestClient, owner: Actor) -> None:
    response = client.post(
        f"{URL}/csv",
        params={"filename": "a.csv"},
        content=CSV,
        headers={"Content-Type": "text/csv", "X-Organization-Id": str(uuid.uuid4())},
    )
    assert response.status_code == 401


def test_upload_is_audited(client: TestClient, owner: Actor, db: Session) -> None:
    _uploaded(client, owner)
    log = db.scalars(select(AuditLog).where(AuditLog.action == "import.uploaded")).one()
    assert log.actor_id == owner.user_id
    assert log.details == {"filename": "leads.csv", "rows": 5}
