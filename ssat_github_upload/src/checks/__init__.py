"""Importing this package registers every check module with checks.base's registry."""

from checks import (  # noqa: F401  (imported for registration side effects)
    fio_006_icf_services,
    fio_007_odata_services,
    grc_001_grc_implemented,
    lan_001_products_versions,
    lan_002_systems_sid,
    lan_005_user_count,
    lan_007_installed_products,
    prv_001_sap_all,
    prv_002_sap_new,
    prv_003_s_develop,
    rfc_002_stored_passwords,
    rfc_003_trusted_rfcs,
    rol_003_derived_roles,
    rol_005_unused_roles,
    rol_006_critical_auth_objects,
    sys_001_profile_parameters,
    sys_002_security_audit_log,
    sys_004_gateway_acl,
    usr_004_dormant_users,
    usr_007_standard_users,
)
from checks.base import CheckResult, CheckSpec, all_check_ids, get_check, get_spec

__all__ = [
    "CheckResult",
    "CheckSpec",
    "all_check_ids",
    "get_check",
    "get_spec",
]
