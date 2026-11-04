from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from leadforge_core.models import AuditLog, Business, MemberRole

from .conftest import Actor

URL = "/api/v1/businesses"


def _create(client: TestClient, actor: Actor, **fields: object) -> dict:  # type: ignore[type-arg]
    payload = {"name": "Riverside Dental", **fields}
    response = client.post(URL, json=payload, headers=actor.headers)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_create_normalizes_url_and_records_audit_log(
    client: TestClient, owner: Actor, db: Session
) -> None:
    body = _create(
        client,
        owner,
        website_url="  WWW.Riverside-Dental.example.com/contact ",
        country_code="gb",
        city="  Leeds ",
    )
    assert body["website_url"] == "https://www.riverside-dental.example.com/contact"
    assert body["domain"] == "riverside-dental.example.com"
    assert body["country_code"] == "GB"
    assert body["city"] == "Leeds"
    assert body["status"] == "new"
    assert body["source"] == "manual"
    assert body["organization_id"] == str(owner.organization_id)

    log = db.scalars(select(AuditLog).where(AuditLog.action == "business.created")).one()
    assert log.actor_id == owner.user_id
    assert str(log.entity_id) == body["id"]


@pytest.mark.parametrize(
    "website_url",
    ["http://localhost:8000", "http://169.254.169.254/", "http://10.0.0.1", "ftp://example.com"],
)
def test_create_rejects_unsafe_urls(client: TestClient, owner: Actor, website_url: str) -> None:
    response = client.post(
        URL, json={"name": "X", "website_url": website_url}, headers=owner.headers
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_create_rejects_client_supplied_ownership_fields(client: TestClient, owner: Actor) -> None:
    for field in ("organization_id", "created_by", "source", "id"):
        response = client.post(
            URL, json={"name": "X", field: str(uuid.uuid4())}, headers=owner.headers
        )
        assert response.status_code == 422, field


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "x" * 201},
        {"name": "X", "status": "bogus"},
        {"name": "X", "country_code": "GBR"},
        {"name": "X", "phone": "call me maybe"},
    ],
)
def test_create_validation(client: TestClient, owner: Actor, payload: dict) -> None:  # type: ignore[type-arg]
    assert client.post(URL, json=payload, headers=owner.headers).status_code == 422


def test_duplicate_domain_conflicts(client: TestClient, owner: Actor) -> None:
    first = _create(client, owner, website_url="https://acme.example.com")
    response = client.post(
        URL,
        json={"name": "Acme again", "website_url": "http://www.acme.example.com/"},
        headers=owner.headers,
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "business_already_exists"
    assert error["details"]["existing_id"] == first["id"]


def test_list_is_paginated_filtered_and_scoped(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    for i in range(7):
        _create(client, owner, name=f"Biz {i}", status="qualified" if i % 2 else "new")
    other = make_actor()
    _create(client, other, name="Biz other-tenant")

    page = client.get(URL, params={"limit": 3, "offset": 0}, headers=owner.headers).json()
    assert page["total"] == 7
    assert page["limit"] == 3
    assert len(page["items"]) == 3
    middle = client.get(URL, params={"limit": 3, "offset": 3}, headers=owner.headers).json()
    rest = client.get(URL, params={"limit": 3, "offset": 6}, headers=owner.headers).json()
    assert len(rest["items"]) == 1
    everything = page["items"] + middle["items"] + rest["items"]
    # Pages are disjoint, complete and ordered newest first.
    assert sorted(b["name"] for b in everything) == [f"Biz {i}" for i in range(7)]
    created = [b["created_at"] for b in everything]
    assert created == sorted(created, reverse=True)

    qualified = client.get(URL, params={"status": "qualified"}, headers=owner.headers).json()
    assert qualified["total"] == 3

    search = client.get(URL, params={"q": "biz 4"}, headers=owner.headers).json()
    assert [b["name"] for b in search["items"]] == ["Biz 4"]
    assert all("other-tenant" not in b["name"] for b in page["items"] + rest["items"])


@pytest.mark.parametrize(
    "params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001}]
)
def test_list_rejects_unbounded_pagination(client: TestClient, owner: Actor, params: dict) -> None:  # type: ignore[type-arg]
    assert client.get(URL, params=params, headers=owner.headers).status_code == 422


def test_search_treats_wildcards_literally(client: TestClient, owner: Actor) -> None:
    _create(client, owner, name="100% Plumbing")
    _create(client, owner, name="Other")
    found = client.get(URL, params={"q": "%"}, headers=owner.headers).json()
    assert [b["name"] for b in found["items"]] == ["100% Plumbing"]


def test_get_and_cross_tenant_isolation(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor]
) -> None:
    created = _create(client, owner)
    assert client.get(f"{URL}/{created['id']}", headers=owner.headers).status_code == 200

    intruder = make_actor()
    response = client.get(f"{URL}/{created['id']}", headers=intruder.headers)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "business_not_found"
    assert client.delete(f"{URL}/{created['id']}", headers=intruder.headers).status_code == 404
    assert client.get(f"{URL}/{uuid.uuid4()}", headers=owner.headers).status_code == 404
    assert client.get(f"{URL}/not-a-uuid", headers=owner.headers).status_code == 422


def test_delete_requires_admin_and_is_audited(
    client: TestClient, owner: Actor, make_actor: Callable[..., Actor], db: Session
) -> None:
    from leadforge_core.models import Organization

    created = _create(client, owner)
    org = db.get(Organization, owner.organization_id)
    member = make_actor(MemberRole.MEMBER, organization=org)

    denied = client.delete(f"{URL}/{created['id']}", headers=member.headers)
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"

    assert client.delete(f"{URL}/{created['id']}", headers=owner.headers).status_code == 204
    assert client.get(f"{URL}/{created['id']}", headers=owner.headers).status_code == 404
    db.expire_all()
    assert db.scalars(select(Business)).all() == []
    assert db.scalars(select(AuditLog).where(AuditLog.action == "business.deleted")).one()
