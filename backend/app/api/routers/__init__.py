from backend.app.api.routers.health import register_health_routes
from backend.app.api.routers.status import register_status_routes


def include_api_routes(app) -> None:
    register_health_routes(app)
    register_status_routes(app)
