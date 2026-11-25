from __future__ import annotations

from fastapi import Depends, Request

from backend.app.auth import AuthenticatedUser, get_authenticated_user
from backend.app.read_models import AuthenticatedIdentityRead


def current_identity(user: AuthenticatedUser, *, request: Request) -> AuthenticatedIdentityRead:
    config = request.app.state.config
    return AuthenticatedIdentityRead(
        username=user.username,
        email=user.email,
        subject=user.subject,
        role_codes=sorted(user.role_codes),
        permissions=sorted(user.permissions),
        auth_mode=user.auth_mode,
        auth_role_source=config.auth_role_source,
        deployment_git_sha=config.deployment_git_sha or None,
    )


def register_identity_routes(app) -> None:
    def get_current_identity(
        request: Request,
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ):
        return current_identity(user, request=request)

    app.add_api_route(
        "/auth/me",
        get_current_identity,
        methods=["GET"],
        response_model=AuthenticatedIdentityRead,
        tags=["auth"],
    )
