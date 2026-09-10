from __future__ import annotations

from fastapi import Depends

from backend.app.auth import AuthenticatedUser, get_authenticated_user
from backend.app.read_models import AuthenticatedIdentityRead


def current_identity(user: AuthenticatedUser) -> AuthenticatedIdentityRead:
    return AuthenticatedIdentityRead(
        username=user.username,
        email=user.email,
        subject=user.subject,
        role_codes=sorted(user.role_codes),
        permissions=sorted(user.permissions),
    )


def register_identity_routes(app) -> None:
    def get_current_identity(
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        return current_identity(user)

    app.add_api_route(
        "/auth/me",
        get_current_identity,
        methods=["GET"],
        response_model=AuthenticatedIdentityRead,
        tags=["auth"],
    )
