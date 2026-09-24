"""RFC connector: talks to a real SAP system via PyRFC + SAP NetWeaver RFC SDK.

Two data-access primitives are used throughout the checks:

- ``read_table``: wraps the standard RFC_READ_TABLE function module for
  generic transparent-table reads (USR02, AGR_1251, AGR_USERS, CVERS, ...).
- ``call_fm``: calls any other remote-enabled function module directly
  (RFC_SYSTEM_INFO, TH_GET_PARAMETER, RFCDES2RFCDISPLAY, ...) for the handful
  of checks where a plain table read isn't the right tool.

Requires: `pip install pyrfc` and the SAP NetWeaver RFC SDK installed and on
the library path (see requirements.txt).
"""

from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Any, Iterable

try:
    from pyrfc import Connection
except ImportError:  # pragma: no cover - optional runtime dependency
    Connection = Any  # type: ignore[assignment]

from .base import SAPConnector

logger = logging.getLogger(__name__)

# RFC_READ_TABLE's DATA work-area is safely usable up to ~480 bytes when a
# DELIMITER is used without the Z_AW_* wide-table add-on being installed.
_MAX_ROW_WIDTH = 480
_OPTIONS_LINE_WIDTH = 72
_ROW_BATCH_SIZE = 1000
_DELIMITER = "\x1e"  # ASCII record separator: extremely unlikely to appear in SAP data
_MAX_RECONNECT_ATTEMPTS = 3
_RECONNECT_BACKOFF_SECONDS = 1.5


class RFCConnectionError(RuntimeError):
    pass


class RFCConnector(SAPConnector):
    def __init__(
        self,
        ashost: str,
        sysnr: str,
        client: str,
        user: str,
        passwd: str,
        lang: str = "EN",
        system_id: str | None = None,
        extra_params: dict[str, Any] | None = None,
    ) -> None:
        self._conn_params = {
            "ashost": ashost,
            "sysnr": sysnr,
            "client": client,
            "user": user,
            "passwd": passwd,
            "lang": lang,
            **(extra_params or {}),
        }
        self._sid = system_id or ""
        self._conn = None

        # Every RFC call this connector makes, across the whole run -- for consultant
        # troubleshooting when a check errors: exactly what was executed against the backend
        # and what came back (or what exception it raised), not just the check's own summary
        # sentence. `current_check_id` is set by run_assessment.run_checks() before each check
        # runs, so every trace entry can be attributed back to the check that caused it; entries
        # recorded outside any check (e.g. connect()'s own RFC_SYSTEM_INFO call) get None.
        self.trace: list[dict[str, Any]] = []
        self.current_check_id: str | None = None

    # -- lifecycle -----------------------------------------------------

    def connect(self) -> None:
        try:
            from pyrfc import Connection
        except ImportError as exc:
            raise RFCConnectionError(
                "pyrfc is not installed / SAP NetWeaver RFC SDK not found. "
                "See requirements.txt / README setup steps."
            ) from exc
        try:
            self._conn = Connection(**self._conn_params)
        except Exception as exc:  # pyrfc raises its own CommunicationError/LogonError
            raise RFCConnectionError(f"Failed to connect to SAP: {exc}") from exc

        if not self._sid:
            info = self.call_fm("RFC_SYSTEM_INFO")
            self._sid = info.get("RFCSI_EXPORT", {}).get("RFCSYSID", "")

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @property
    def system_id(self) -> str:
        return self._sid

    def _reconnect(self) -> None:
        try:
            self._conn.close()  # release the dead handle before opening a new one
        except Exception:  # noqa: BLE001 - it's already broken; best effort only
            pass
        time.sleep(_RECONNECT_BACKOFF_SECONDS)
        from pyrfc import Connection

        self._conn = Connection(**self._conn_params)

    # -- generic FM call -------------------------------------------------

    def call_fm(self, name: str, **params: Any) -> dict[str, Any]:
        if self._conn is None:
            raise RFCConnectionError("Not connected. Use as a context manager or call connect() first.")

        last_exc: Exception | None = None
        for attempt in range(1 + _MAX_RECONNECT_ATTEMPTS):
            try:
                result = self._conn.call(name, **params)
                self._record_trace(name, params, result=result)
                return result
            except Exception as exc:
                self._record_trace(name, params, error=exc)
                if not self._is_connection_dead(exc) or attempt == _MAX_RECONNECT_ATTEMPTS:
                    raise
                last_exc = exc
                logger.warning(
                    "RFC connection appears dead (%s); reconnecting and retrying %s (attempt %s/%s).",
                    exc, name, attempt + 1, _MAX_RECONNECT_ATTEMPTS,
                )
                self._reconnect()
        raise last_exc  # unreachable, satisfies type checkers

    @staticmethod
    def _is_connection_dead(exc: Exception) -> bool:
        return type(exc).__name__ in ("CommunicationError", "ExternalRuntimeError")

    # -- call trace, for consultant troubleshooting -----------------------

    def _record_trace(self, name: str, params: dict[str, Any], result: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        if name == "RFC_READ_TABLE":
            where = " ".join(o.get("TEXT", "") for o in params.get("OPTIONS", []))
            call_desc = f"RFC_READ_TABLE {params.get('QUERY_TABLE', '?')}" + (f" WHERE {where}" if where else "")
            outcome = f"{len(result.get('DATA', []))} row(s)" if result is not None else None
        elif name == "TH_GET_PARAMETER":
            # Called once per profile parameter (e.g. 19x for SYS-001's baseline) -- without the
            # parameter name, every one of those calls would look identical in the trace.
            call_desc = f"TH_GET_PARAMETER {params.get('PARAMETER_NAME', '?')}"
            outcome = f"= {result.get('PARAMETER_VALUE')!r}" if result is not None else None
        else:
            call_desc = name
            outcome = "OK" if result is not None else None

        self.trace.append(
            {
                "ts": _dt.datetime.now().isoformat(timespec="seconds"),
                "check_id": self.current_check_id,
                "call": call_desc,
                "ok": error is None,
                "detail": outcome if error is None else f"{type(error).__name__}: {error}",
            }
        )

    # -- table read --------------------------------------------------------

    def read_table(
        self,
        table_name: str,
        fields: Iterable[str] | None = None,
        where: str | None = None,
        max_rows: int = 0,
        batch_size: int = _ROW_BATCH_SIZE,
    ) -> list[dict[str, str]]:
        """`batch_size` overrides the default 1000-row page size. Some tables on some systems
        (seen live on AGR_USERS, which goes through a HANA CDS-pushed-down access path on this
        landscape) don't return a stable row partition across separate paginated RFC_READ_TABLE
        calls when there's no ORDER BY -- the total row count across pages stays correct, but
        which physical rows land in which page can shift between calls, so accumulated content
        differs run to run. Passing a batch_size that covers the whole table in one call sidesteps
        that entirely, since there's then no cross-call boundary for rows to fall on either side of.
        """
        field_table = [{"FIELDNAME": f.upper()} for f in fields] if fields else []
        options_table = self._build_options(where)

        rows: list[dict[str, str]] = []
        rowskip = 0
        field_order: list[str] | None = None

        while True:
            call_size = batch_size
            if max_rows:
                remaining = max_rows - len(rows)
                if remaining <= 0:
                    break
                call_size = min(call_size, remaining)

            result = self.call_fm(
                "RFC_READ_TABLE",
                QUERY_TABLE=table_name.upper(),
                DELIMITER=_DELIMITER,
                FIELDS=field_table,
                OPTIONS=options_table,
                ROWSKIPS=rowskip,
                ROWCOUNT=call_size,
            )

            if field_order is None:
                returned_fields = result.get("FIELDS", [])
                field_order = [f["FIELDNAME"] for f in returned_fields]
                total_width = sum(int(f.get("LENGTH", 0) or 0) for f in returned_fields)
                if total_width > _MAX_ROW_WIDTH:
                    logger.warning(
                        "%s: selected field width %s exceeds the safe RFC_READ_TABLE "
                        "row limit (%s); rows may be truncated. Narrow the `fields` list.",
                        table_name,
                        total_width,
                        _MAX_ROW_WIDTH,
                    )

            data_rows = result.get("DATA", [])
            for row in data_rows:
                values = row["WA"].split(_DELIMITER)
                rows.append(dict(zip(field_order, values)))

            if len(data_rows) < call_size:
                break
            rowskip += len(data_rows)

        return rows

    @staticmethod
    def _build_options(where: str | None) -> list[dict[str, str]]:
        if not where:
            return []
        options = []
        remaining = where.strip()
        while remaining:
            options.append({"TEXT": remaining[:_OPTIONS_LINE_WIDTH]})
            remaining = remaining[_OPTIONS_LINE_WIDTH:]
        return options
