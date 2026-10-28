"""Real mapped Case/DocumentVersion/StorageBinding owner-gate concurrency.

Only opt-in disposable loopback PostgreSQL with migrated application tables.
No production database, NAS or storage adapter is accessed.
"""
from hashlib import sha256
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.db.enums import CaseState, DocumentVariantType
from backend.app.db.models.phase1 import (
    Company, Site, Case, Document, DocumentVariant, DocumentVersion, StorageBinding,
)
from backend.app.document.inspection_qd_kt_draft_provenance import QdKtDraftProvenance
from backend.app.document.inspection_qd_kt_draft_storage_audit import (
    QdKtDraftStorageAuditBlocked, resolve_qdkt_draft_storage_locator,
)
from test_inspection_qd_kt_transaction_visibility_postgres import _checked_ci_url


def _new_id():
    return str(uuid4())


@pytest.mark.parametrize("isolation,observes_commit", [
    ("READ COMMITTED", True),
    ("REPEATABLE READ", False),
])
@pytest.mark.parametrize("mutation", ["binding_owner", "binding_path", "version_binding"])
def test_real_orm_locator_concurrent_owner_mutation(isolation, observes_commit, mutation):
    engine = create_engine(_checked_ci_url())
    ids = {key: _new_id() for key in (
        "company", "site", "case1", "case2", "document", "variant", "version",
        "binding1", "binding2",
    )}
    folder = "qdkt-orm-" + ids["case1"]
    original_path = folder + "/draft.docx"
    digest = sha256(b"synthetic-only-owner-probe").hexdigest()
    provenance = QdKtDraftProvenance(
        case_id=ids["case1"], draft_id="offline-draft",
        document_version_id=ids["version"], document_id=ids["document"],
        stored_checksum_sha256=digest, team_id="offline-team",
        team_revision=1, ordered_member_ids=("offline-member",),
    )
    try:
        # Exercise the production-mapped tables, not a synthetic lookalike schema.
        # CI has already migrated the disposable database before this test step.
        with engine.begin() as conn:
            conn.execute(Company.__table__.insert().values(
                id=ids["company"], legal_name="Disposable QDKT ORM fixture",
            ))
            conn.execute(Site.__table__.insert().values(
                id=ids["site"], company_id=ids["company"], site_name="Fixture site",
            ))
            for key in ("case1", "case2"):
                conn.execute(Case.__table__.insert().values(
                    id=ids[key], site_id=ids["site"], gxp_type="GMP", state=CaseState.DRAFT,
                ))
            conn.execute(Document.__table__.insert().values(
                id=ids["document"], case_id=ids["case1"],
                family_code="INSPECTION_QD_KT", document_type_code="INSPECTION_QD_KT",
            ))
            conn.execute(DocumentVariant.__table__.insert().values(
                id=ids["variant"], document_id=ids["document"],
                variant_type=DocumentVariantType.EDITABLE_DOCX, language_code="vi",
            ))
            conn.execute(StorageBinding.__table__.insert(), [
                dict(id=ids["binding1"], case_id=ids["case1"],
                     relative_path=folder, storage_class="local_filesystem_fake"),
                dict(id=ids["binding2"], case_id=ids["case2"],
                     relative_path="other-"+ids["case2"], storage_class="local_filesystem_fake"),
            ])
            conn.execute(DocumentVersion.__table__.insert().values(
                id=ids["version"], document_variant_id=ids["variant"], version_no=1,
                storage_binding_id=ids["binding1"], storage_root="inspection",
                storage_relative_path=original_path, checksum_sha256=digest,
            ))
        with (
            engine.connect().execution_options(isolation_level=isolation) as reader_conn,
            Session(reader_conn, autoflush=False) as reader,
            Session(engine, autoflush=False) as writer,
        ):
            initial = resolve_qdkt_draft_storage_locator(reader, provenance=provenance)
            assert initial.storage_binding_owner_verified
            if mutation == "binding_owner":
                stmt = StorageBinding.__table__.update().where(
                    StorageBinding.id == ids["binding1"]
                ).values(case_id=ids["case2"])
            elif mutation == "binding_path":
                stmt = StorageBinding.__table__.update().where(
                    StorageBinding.id == ids["binding1"]
                ).values(relative_path="relocated-"+ids["case2"])
            else:
                stmt = DocumentVersion.__table__.update().where(
                    DocumentVersion.id == ids["version"]
                ).values(storage_binding_id=ids["binding2"])
            writer.execute(stmt)
            # A writer's pending change must not become visible to reader.
            assert resolve_qdkt_draft_storage_locator(reader, provenance=provenance) == initial
            writer.commit()
            if observes_commit:
                with pytest.raises(QdKtDraftStorageAuditBlocked, match="OWNER_MISMATCH"):
                    resolve_qdkt_draft_storage_locator(reader, provenance=provenance)
            else:
                # REPEATABLE READ preserves original snapshot, despite ORM refresh.
                assert resolve_qdkt_draft_storage_locator(reader, provenance=provenance) == initial
            reader.rollback()
    finally:
        # Delete only our UUID-scoped fixture, never truncate application tables.
        with engine.begin() as conn:
            conn.execute(DocumentVersion.__table__.delete().where(DocumentVersion.id == ids["version"]))
            conn.execute(StorageBinding.__table__.delete().where(StorageBinding.id.in_(
                [ids["binding1"], ids["binding2"]]
            )))
            conn.execute(DocumentVariant.__table__.delete().where(DocumentVariant.id == ids["variant"]))
            conn.execute(Document.__table__.delete().where(Document.id == ids["document"]))
            conn.execute(Case.__table__.delete().where(Case.id.in_([ids["case1"], ids["case2"]])))
            conn.execute(Site.__table__.delete().where(Site.id == ids["site"]))
            conn.execute(Company.__table__.delete().where(Company.id == ids["company"]))
        engine.dispose()
