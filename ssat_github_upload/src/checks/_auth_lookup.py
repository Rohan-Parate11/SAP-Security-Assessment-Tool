"""Shared "who has X" lookups reused by the privileged-access checks.

RFC_READ_TABLE has no server-side JOIN, so a "who has SAP_ALL" style question
is answered with two or three separate reads stitched together in Python:
role/profile definition tables -> AGR_USERS (role-to-user assignment).
"""

from __future__ import annotations

import datetime as _dt

from connectors.base import SAPConnector


def roles_with_auth_object(connector: SAPConnector, object_name: str) -> list[str]:
    """Role names (AGR_NAME) that maintain the given authorization object."""
    rows = connector.read_table(
        "AGR_1251",
        fields=["AGR_NAME"],
        where=f"OBJECT = '{object_name}'",
    )
    return sorted({r["AGR_NAME"].strip() for r in rows if r.get("AGR_NAME")})


def roles_with_profile(connector: SAPConnector, profile_name: str) -> list[str]:
    """Role names (AGR_NAME) whose generated profile matches profile_name."""
    rows = connector.read_table(
        "AGR_PROF",
        fields=["AGR_NAME"],
        where=f"PROFILE = '{profile_name}'",
    )
    return sorted({r["AGR_NAME"].strip() for r in rows if r.get("AGR_NAME")})


# Confirmed live: on this landscape, AGR_* tables are served through a HANA CDS-pushed-down
# access path that doesn't return a stable row partition across separate paginated RFC_READ_TABLE
# calls (no ORDER BY support). Total row count across pages is still arithmetically correct, but
# WHICH physical rows land in which page shifts between calls, so anything that depends on row
# identity/membership (a Python set of names, a per-role grouping) -- not just a raw count -- can
# come out different on every run of an otherwise-unchanged table. Any full, unfiltered read of an
# AGR_* table large enough to need more than one page (over ~1000 rows) should pass this as
# batch_size, so it completes in a single call with no cross-call boundary to land on either side of.
LARGE_TABLE_BATCH_SIZE = 50_000


def active_users_for_roles(connector: SAPConnector, role_names: list[str]) -> list[dict[str, str]]:
    """Active (non-expired) AGR_USERS assignments for the given roles.

    Filters entirely in Python rather than pushing an OR-chain of role names
    into the WHERE clause: on a live S/4HANA 758 sandbox, this system's
    AGR_USERS access path (message class SAIS -- a HANA/CDS-pushed-down
    read, not classic Open SQL) rejected long OR-chains outright, regardless
    of how they were split across RFC_READ_TABLE's 72-char OPTIONS lines.
    AGR_USERS is small enough (thousands of rows, not millions) that one
    unfiltered-by-role read per call is cheap and avoids that landmine.

    Also read in a single RFC_READ_TABLE call rather than the default 1000-row
    pagination: confirmed live that this same access path doesn't return a
    stable row partition across separate paginated calls (row count per call
    stayed correct, but which physical rows landed in which page shifted
    between calls, so three otherwise-identical assessment runs produced three
    different user counts). A single call has no cross-call boundary for rows
    to land inconsistently across.
    """
    if not role_names:
        return []
    today = _dt.date.today().strftime("%Y%m%d")
    role_set = set(role_names)
    rows = connector.read_table(
        "AGR_USERS",
        fields=["AGR_NAME", "UNAME", "FROM_DAT", "TO_DAT"],
        where=f"FROM_DAT <= '{today}' AND TO_DAT >= '{today}'",
        batch_size=LARGE_TABLE_BATCH_SIZE,
    )
    return [row for row in rows if row.get("AGR_NAME", "").strip() in role_set]


def users_with_direct_profile(connector: SAPConnector, profile_name: str) -> list[dict[str, str]]:
    """Users with profile_name assigned directly (not via a role), from UST04."""
    return connector.read_table(
        "UST04",
        fields=["BNAME", "PROFILE"],
        where=f"PROFILE = '{profile_name}'",
    )


def users_with_profile(connector: SAPConnector, profile_name: str) -> list[dict[str, str]]:
    """Combine role-based and direct profile assignment for e.g. SAP_ALL."""
    findings: list[dict[str, str]] = []

    roles = roles_with_profile(connector, profile_name)
    for row in active_users_for_roles(connector, roles):
        findings.append(
            {
                "user": row.get("UNAME", "").strip(),
                "assignment_type": "role",
                "role_name": row.get("AGR_NAME", "").strip(),
                "from_date": row.get("FROM_DAT", "").strip(),
                "to_date": row.get("TO_DAT", "").strip(),
            }
        )

    for row in users_with_direct_profile(connector, profile_name):
        findings.append(
            {
                "user": row.get("BNAME", "").strip(),
                "assignment_type": "direct_profile",
                "role_name": None,
                "from_date": None,
                "to_date": None,
            }
        )

    return findings


def users_with_auth_object(connector: SAPConnector, object_name: str) -> list[dict[str, str]]:
    roles = roles_with_auth_object(connector, object_name)
    findings = []
    for row in active_users_for_roles(connector, roles):
        findings.append(
            {
                "user": row.get("UNAME", "").strip(),
                "role_name": row.get("AGR_NAME", "").strip(),
                "from_date": row.get("FROM_DAT", "").strip(),
                "to_date": row.get("TO_DAT", "").strip(),
            }
        )
    return findings


def user_status(connector: SAPConnector, usernames: set[str], dormant_days: int = 90) -> dict[str, dict]:
    """Lock status + last-logon for a set of usernames, read from USR02 in one full-table pass.

    Deliberately not filtered by a WHERE on BNAME: this system's AGR_USERS access path already
    rejected long OR-chains outright (see active_users_for_roles), and USR02 is small enough
    (hundreds, not millions, of rows) that one unfiltered read is cheap and avoids the same risk.
    """
    if not usernames:
        return {}
    today = _dt.date.today()
    rows = connector.read_table("USR02", fields=["BNAME", "UFLAG", "TRDAT"])
    status: dict[str, dict] = {}
    for r in rows:
        bname = r.get("BNAME", "").strip()
        if bname not in usernames:
            continue
        uflag = r.get("UFLAG", "").strip()
        trdat = r.get("TRDAT", "").strip()
        last_logon, days_since = None, None
        if trdat and trdat != "00000000":
            last_logon = f"{trdat[0:4]}-{trdat[4:6]}-{trdat[6:8]}"
            days_since = (today - _dt.date(int(trdat[0:4]), int(trdat[4:6]), int(trdat[6:8]))).days
        locked = uflag not in ("", "0")
        status[bname] = {
            "locked": locked,
            "last_logon_date": last_logon,
            "days_since_last_logon": days_since,
            "dormant": not locked and (days_since is None or days_since > dormant_days),
        }
    return status
