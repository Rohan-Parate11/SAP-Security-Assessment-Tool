"""Minimal OData connector for the one check that needs the Gateway REST API
rather than a backend RFC table read: the SAP Gateway service catalog isn't
exposed through a documented, stable transparent table, but SAP does publish
a supported OData endpoint for it (CATALOGSERVICE). See fio_007_odata_services.

This is deliberately small -- a single GET wrapper with basic auth -- not a
general-purpose OData client, per the connector-agnostic architecture: add
more methods here only when another check actually needs them.
"""

from __future__ import annotations

from typing import Any

import requests


class ODataConnector:
    def __init__(self, base_url: str, client: str, user: str, passwd: str, verify_ssl: bool = True) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._auth = (user, passwd)
        self._verify_ssl = verify_ssl

    def get_json(self, path: str, extra_params: dict[str, str] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        params = {"sap-client": self._client, "$format": "json", **(extra_params or {})}
        response = requests.get(
            url,
            params=params,
            auth=self._auth,
            headers={"Accept": "application/json"},
            verify=self._verify_ssl,
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def get_service_catalog(self) -> list[dict[str, Any]]:
        """OData V2 service catalog (SAP Gateway CATALOGSERVICE)."""
        data = self.get_json("/sap/opu/odata/IWFND/CATALOGSERVICE;v=2/ServiceCollection")
        return data.get("d", {}).get("results", [])

    def get_service_catalog_v4(self) -> list[dict[str, Any]]:
        """OData V4 service catalog -- a separate registry from the V2 one above, so a system
        with V4-only services would otherwise be invisible to this tool. V4 JSON responses use
        the standard top-level "value" array, not V2's "d.results" envelope."""
        data = self.get_json("/sap/opu/odata4/iwbep/all/default/iwfnd/catalog/0002/ServiceGroups")
        return data.get("value", [])
