from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.models.phase1 import Case, Company, Site


class CatalogReadService:
    def list_companies(self, session: Session, *, q: str | None, limit: int):
        stmt = select(Company).order_by(Company.legacy_company_id).limit(limit)
        if q:
            stmt = stmt.where(Company.legal_name.ilike(f"%{q}%"))
        return list(session.scalars(stmt))

    def get_company(self, session: Session, company_id: str) -> Company:
        row = session.get(Company, company_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Company not found.")
        return row

    def list_sites(self, session: Session, *, q: str | None, limit: int):
        stmt = select(Site).order_by(Site.legacy_site_id).limit(limit)
        if q:
            stmt = stmt.where(Site.site_name.ilike(f"%{q}%"))
        return list(session.scalars(stmt))

    def get_site(self, session: Session, site_id: str) -> Site:
        row = session.get(Site, site_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Site not found.")
        return row

    def list_cases(self, session: Session, *, q: str | None, gxp_type: str | None, limit: int):
        stmt = select(Case).order_by(Case.legacy_inspection_id).limit(limit)
        if q:
            stmt = stmt.where(Case.legacy_inspection_code.ilike(f"%{q}%"))
        if gxp_type:
            stmt = stmt.where(Case.gxp_type == gxp_type)
        return list(session.scalars(stmt))

    def get_case(self, session: Session, case_id: str) -> Case:
        row = session.get(Case, case_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Case not found.")
        return row
