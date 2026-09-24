"""Connector interface that assessment checks are written against.

Per the architecture principle in SAP_Security_Framework_Assessment_Context.md,
checks must not depend on the transport mechanism. A check only calls
``read_table`` / ``call_fm`` on whatever connector it is given.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable


class SAPConnector(ABC):
    """Abstract base for all connector implementations (RFC, OData, file import, ...)."""

    def __enter__(self) -> "SAPConnector":
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    @abstractmethod
    def connect(self) -> None:
        """Open the underlying connection."""

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""

    @abstractmethod
    def read_table(
        self,
        table_name: str,
        fields: Iterable[str] | None = None,
        where: str | None = None,
        max_rows: int = 0,
    ) -> list[dict[str, str]]:
        """Return rows of a table as a list of dicts keyed by field name.

        Args:
            table_name: transparent table name, e.g. "USR02".
            fields: field names to return; keep the total selected field
                width well under ~480 characters (RFC_READ_TABLE's row-buffer
                limit) -- pass a curated list rather than None for wide tables.
            where: a single ABAP WHERE-clause string, e.g.
                "BNAME = 'SAP*' OR BNAME = 'DDIC'". The connector is
                responsible for chunking it into 72-character OPTIONS lines.
            max_rows: 0 means "no limit" (connector paginates internally).
        """

    @abstractmethod
    def call_fm(self, name: str, **params: Any) -> dict[str, Any]:
        """Call a remote-enabled function module and return its export/tables."""

    @property
    @abstractmethod
    def system_id(self) -> str:
        """SID (or logical identifier) of the connected system."""
