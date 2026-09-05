from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.base import Base
from backend.app.db.models.phase1 import AppUser, AppUserRole, RbacRole
from backend.app.rbac import ensure_builtin_rbac_baseline, provision_app_user
from tools import verify_rbac_readiness as readiness


def _database_url(path: Path) -> str:
    engine = create_engine(f"sqlite:///{path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    engine.dispose()
    return f"sqlite:///{path.as_posix()}"


def _seed_baseline(url: str) -> None:
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        ensure_builtin_rbac_baseline(session)
        session.commit()
    engine.dispose()


def _seed_user(url: str, *, email: str, role_code: str, active: bool = True) -> None:
    engine = create_engine(url, future=True)
    with Session(engine) as session:
        provision_app_user(
            session,
            username=email.split("@", 1)[0],
            email=email,
            role_code=role_code,
        )
        app_user = session.query(AppUser).filter_by(external_email=email.lower()).one()
        app_user.is_active = active
        session.commit()
    engine.dispose()


def test_baseline_only_passes_without_named_users(tmp_path: Path, capsys) -> None:
    url = _database_url(tmp_path / "arbitrary-target.sqlite")
    _seed_baseline(url)

    assert readiness.main(["--database-url", url]) == 0
    assert capsys.readouterr().out.splitlines() == ["RBAC_BASELINE=PASS", "STATUS=RBAC_READINESS_PASS"]


def test_invalid_baseline_fails_closed(tmp_path: Path, capsys) -> None:
    url = _database_url(tmp_path / "missing-baseline.sqlite")

    assert readiness.main(["--database-url", url]) == 1
    captured = capsys.readouterr()
    assert "Missing required RBAC permission" in captured.err
    assert captured.err.rstrip().endswith("STATUS=RBAC_READINESS_FAIL")


def test_required_active_user_with_exact_role_passes_and_normalizes(tmp_path: Path, capsys) -> None:
    url = _database_url(tmp_path / "identity.sqlite")
    _seed_baseline(url)
    _seed_user(url, email="operator@example.invalid", role_code="manager")

    assert readiness.main(["--database-url", url, "--require-user", " Operator@Example.Invalid : MANAGER "]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "RBAC_BASELINE=PASS",
        "REQUIRED_USER=operator@example.invalid|ROLE=manager|STATUS=PASS",
        "STATUS=RBAC_READINESS_PASS",
    ]


def test_required_user_absent_inactive_or_without_role_fails(tmp_path: Path, capsys) -> None:
    url = _database_url(tmp_path / "required-user-failures.sqlite")
    _seed_baseline(url)
    _seed_user(url, email="inactive@example.invalid", role_code="admin", active=False)
    _seed_user(url, email="reader@example.invalid", role_code="reader")

    assert readiness.main(["--database-url", url, "--require-user", "missing@example.invalid:admin"]) == 1
    assert "Required user is absent" in capsys.readouterr().err
    assert readiness.main(["--database-url", url, "--require-user", "inactive@example.invalid:admin"]) == 1
    assert "Required user is inactive" in capsys.readouterr().err
    assert readiness.main(["--database-url", url, "--require-user", "reader@example.invalid:manager"]) == 1
    assert "lacks exact role manager" in capsys.readouterr().err


def test_multiple_requirements_pass_only_when_all_valid_and_duplicates_are_deduplicated(tmp_path: Path, capsys) -> None:
    url = _database_url(tmp_path / "multiple.sqlite")
    _seed_baseline(url)
    _seed_user(url, email="a@example.invalid", role_code="admin")
    _seed_user(url, email="b@example.invalid", role_code="manager")

    assert readiness.main(
        [
            "--database-url", url,
            "--require-user", "a@example.invalid:admin",
            "--require-user", " A@EXAMPLE.INVALID : ADMIN ",
            "--require-user", "b@example.invalid:manager",
        ]
    ) == 0
    assert capsys.readouterr().out.count("REQUIRED_USER=") == 2
    assert readiness.main(
        [
            "--database-url", url,
            "--require-user", "a@example.invalid:admin",
            "--require-user", "missing@example.invalid:manager",
        ]
    ) == 1
    assert "STATUS=RBAC_READINESS_FAIL" in capsys.readouterr().err


def test_malformed_requirement_fails_before_database_connection(tmp_path: Path, monkeypatch, capsys) -> None:
    called = False

    def unexpected_factory(_url: str):
        nonlocal called
        called = True
        raise AssertionError("database connection should not be attempted")

    monkeypatch.setattr(readiness, "build_session_factory", unexpected_factory)

    assert readiness.main(["--database-url", f"sqlite:///{tmp_path / 'unused.sqlite'}", "--require-user", "missing-role"]) == 1
    assert called is False
    assert "EMAIL:ROLE" in capsys.readouterr().err


def test_missing_database_url_uses_fail_closed_status_output(capsys) -> None:
    assert readiness.main([]) == 1
    assert "STATUS=RBAC_READINESS_FAIL" in capsys.readouterr().err


def test_verifier_is_read_only_and_uses_explicit_target_url(tmp_path: Path, monkeypatch) -> None:
    target_url = _database_url(tmp_path / "target.sqlite")
    other_url = _database_url(tmp_path / "other.sqlite")
    _seed_baseline(target_url)
    _seed_baseline(other_url)
    _seed_user(target_url, email="target@example.invalid", role_code="admin")
    captured_urls: list[str] = []
    real_factory = readiness.build_session_factory

    def capture_factory(url: str):
        captured_urls.append(url)
        return real_factory(url)

    monkeypatch.setattr(readiness, "build_session_factory", capture_factory)
    before_engine = create_engine(target_url, future=True)
    with Session(before_engine) as session:
        before = (session.query(AppUser).count(), session.query(AppUserRole).count(), session.query(RbacRole).count())
    before_engine.dispose()

    readiness.verify_rbac_readiness(
        database_url=target_url,
        required_users=(readiness.RequiredUser("target@example.invalid", "admin"),),
    )

    after_engine = create_engine(target_url, future=True)
    with Session(after_engine) as session:
        after = (session.query(AppUser).count(), session.query(AppUserRole).count(), session.query(RbacRole).count())
    after_engine.dispose()
    assert captured_urls == [target_url]
    assert other_url not in captured_urls
    assert after == before


def test_database_error_does_not_echo_password(tmp_path: Path, capsys) -> None:
    password = "do-not-print-this-password"
    url = f"postgresql://user:{password}@127.0.0.1:1/unavailable"

    assert readiness.main(["--database-url", url]) == 1
    captured = capsys.readouterr()
    assert password not in captured.out
    assert password not in captured.err
    assert "STATUS=RBAC_READINESS_FAIL" in captured.err
