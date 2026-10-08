"""Enterprise menu identity; original portal APIs still enforce business access."""

from typing import Literal

BusinessRole = Literal["unassigned", "employee", "general_manager"]
DepartmentCode = Literal["product", "hr", "engineering"]
DEPARTMENTS = ("product", "hr", "engineering")


def enterprise_identity(user) -> dict:
    """Derive menu capabilities from the current DB user, never JWT claims."""
    role = getattr(user, "business_role", None) or "unassigned"
    department = getattr(user, "department_code", None)
    if role == "general_manager":
        capabilities = ["general_manager", *DEPARTMENTS]
    elif role == "employee" and department in DEPARTMENTS:
        capabilities = [department]
    else:
        role, department, capabilities = "unassigned", None, []
    return {
        "business_role": role,
        "department_code": department if department in DEPARTMENTS else None,
        "portal_user_id": getattr(user, "portal_user_id", None),
        "capabilities": capabilities,
    }
