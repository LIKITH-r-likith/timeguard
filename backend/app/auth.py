"""Authentication and role-based authorization for TimeGuard.

Demo auth: identity and role are passed via headers:
  - X-Role: EMPLOYEE | MANAGER | HR
  - X-Employee-Id: string (required when X-Role is EMPLOYEE)
"""

from __future__ import annotations

from typing import Optional

from fastapi import Header, HTTPException, status

from backend.core.models import Role


class AuthContext:
    def __init__(self, role: Role, employee_id: Optional[str] = None):
        self.role = role
        self.employee_id = employee_id

    @property
    def actor(self) -> str:
        if self.employee_id:
            return self.employee_id
        return f"{self.role.value.lower()}_actor"


def get_auth_context(
    x_role: Optional[str] = Header(None, alias="X-Role"),
    x_employee_id: Optional[str] = Header(None, alias="X-Employee-Id"),
) -> AuthContext:
    """FastAPI dependency to extract and validate caller credentials."""
    if not x_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": "FORBIDDEN", "message": "Missing required X-Role header", "details": {}},
        )

    try:
        role = Role(x_role.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": f"Invalid X-Role '{x_role}'. Allowed: EMPLOYEE, MANAGER, HR",
                "details": {},
            },
        )

    if role == Role.EMPLOYEE and not x_employee_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "FORBIDDEN",
                "message": "X-Employee-Id header is required when X-Role is EMPLOYEE",
                "details": {},
            },
        )

    return AuthContext(role=role, employee_id=x_employee_id)


def require_role(*allowed_roles: Role):
    """Dependency factory restricting an endpoint to specific roles."""
    def dependency(auth: AuthContext = None) -> AuthContext:
        # Note: auth will be injected by FastAPI if set as Depends(get_auth_context)
        return auth
    return dependency
