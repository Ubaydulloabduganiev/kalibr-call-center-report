from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import httpx

from .config import Settings


class KommoError(RuntimeError):
    pass


class KommoClient:
    def __init__(self, settings: Settings):
        if not settings.kommo_subdomain or not settings.kommo_long_lived_token:
            raise KommoError("KOMMO_SUBDOMAIN and KOMMO_LONG_LIVED_TOKEN are required")
        self.settings = settings
        self.client = httpx.Client(
            base_url=settings.kommo_base_url,
            headers={
                "Authorization": f"Bearer {settings.kommo_long_lived_token}",
                "Accept": "application/json",
            },
            timeout=30,
        )
        self._minimum_interval = 1 / max(settings.kommo_requests_per_second, 1)
        self._last_request = 0.0

    def close(self) -> None:
        self.client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._minimum_interval:
            time.sleep(self._minimum_interval - elapsed)

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        for attempt in range(5):
            self._throttle()
            response = self.client.get(path, params=params)
            self._last_request = time.monotonic()
            if response.status_code == 204:
                return None
            if response.status_code == 429:
                time.sleep(min(2**attempt, 8))
                continue
            if response.status_code >= 400:
                raise KommoError(f"Kommo GET {path} failed: {response.status_code} {response.text[:500]}")
            return response.json()
        raise KommoError(f"Kommo GET {path} exceeded retries")

    def paginate(
        self,
        path: str,
        embedded_key: str,
        params: dict[str, Any] | None = None,
    ) -> Iterator[dict[str, Any]]:
        page = 1
        base_params = dict(params or {})
        base_params.setdefault("limit", 250)
        while True:
            page_params = {**base_params, "page": page}
            payload = self.get(path, page_params)
            if not payload:
                return
            items = payload.get("_embedded", {}).get(embedded_key, [])
            if not items:
                return
            yield from items
            next_link = payload.get("_links", {}).get("next", {}).get("href")
            if not next_link and len(items) < int(base_params["limit"]):
                return
            page += 1

    def users(self) -> list[dict[str, Any]]:
        return list(self.paginate("/api/v4/users", "users", {"with": "role,group"}))

    def user(self, user_id: int) -> dict[str, Any]:
        payload = self.get(f"/api/v4/users/{user_id}", {"with": "role,group"})
        if not payload:
            raise KommoError(f"Kommo user {user_id} not found")
        return payload

    def roles(self) -> list[dict[str, Any]]:
        return list(self.paginate("/api/v4/roles", "roles"))

    def pipelines(self) -> list[dict[str, Any]]:
        return list(self.paginate("/api/v4/leads/pipelines", "pipelines"))

    def custom_fields(self, entity_type: str) -> list[dict[str, Any]]:
        return list(self.paginate(f"/api/v4/{entity_type}/custom_fields", "custom_fields"))

    def account(self) -> dict[str, Any]:
        return self.get("/api/v4/account", {"with": "task_types,users_groups"}) or {}

    def contacts(self, updated_from: int | None = None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"order[updated_at]": "asc"}
        if updated_from:
            params["filter[updated_at][from]"] = updated_from
        yield from self.paginate("/api/v4/contacts", "contacts", params)

    def leads(self, updated_from: int | None = None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"order[updated_at]": "asc", "with": "contacts"}
        if updated_from:
            params["filter[updated_at][from]"] = updated_from
        yield from self.paginate("/api/v4/leads", "leads", params)

    def tasks(self, updated_from: int | None = None) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"order[updated_at]": "asc"}
        if updated_from:
            params["filter[updated_at][from]"] = updated_from
        yield from self.paginate("/api/v4/tasks", "tasks", params)

    def notes(
        self,
        entity_type: str,
        updated_from: int | None = None,
        note_types: list[str] | None = None,
    ) -> Iterator[dict[str, Any]]:
        params: dict[str, Any] = {"order[updated_at]": "asc"}
        if updated_from:
            params["filter[updated_at][from]"] = updated_from
        for i, note_type in enumerate(note_types or []):
            params[f"filter[note_type][{i}]"] = note_type
        yield from self.paginate(f"/api/v4/{entity_type}/notes", "notes", params)
