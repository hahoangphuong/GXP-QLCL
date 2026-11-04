"""EXPERIMENTAL_CONTRACT_PROOF: disposable schema; never imported by application."""
import os
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

@pytest.fixture
def proof():
    url=os.environ['CODEX_PROOF_DB_URL']
    assert url.startswith('postgresql+psycopg://codex_probe:') and '@127.0.0.1:55439/gxp_qlcl_test' in url
    admin=create_engine(url); schema='codex_receipt_'+uuid4().hex
    with admin.begin() as c: c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    with engine.begin() as c:
        c.execute(text('CREATE TABLE receipt (op_id text PRIMARY KEY, actor text NOT NULL, site text NOT NULL, fingerprint text NOT NULL, result_id int)'))
        c.execute(text('CREATE TABLE business (id serial PRIMARY KEY, site text NOT NULL)'))
        c.execute(text('CREATE TABLE audit (id serial PRIMARY KEY, business_id int NOT NULL REFERENCES business(id))'))
        c.execute(text('ALTER TABLE receipt ADD CONSTRAINT receipt_result_fk FOREIGN KEY (result_id) REFERENCES business(id) DEFERRABLE INITIALLY DEFERRED'))
        c.execute(text('''CREATE FUNCTION require_receipt_result() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF EXISTS (SELECT 1 FROM receipt WHERE op_id = NEW.op_id AND result_id IS NULL) THEN
                RAISE EXCEPTION 'committed receipt has no result' USING ERRCODE = '23514';
              END IF;
              RETURN NULL;
            END $$'''))
        c.execute(text('''CREATE CONSTRAINT TRIGGER receipt_result_required
            AFTER INSERT OR UPDATE ON receipt DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION require_receipt_result()'''))
    try: yield engine
    finally:
        engine.dispose()
        with admin.begin() as c: c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()

def prepare(c, op='op-a', actor='actor-a', site='site-a', fingerprint='hash-a'):
    c.execute(text('INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES (:op,:actor,:site,:fp)'), {'op':op,'actor':actor,'site':site,'fp':fingerprint})
    business_id=c.scalar(text('INSERT INTO business(site) VALUES (:site) RETURNING id'), {'site':site})
    c.execute(text('INSERT INTO audit(business_id) VALUES (:id)'), {'id':business_id})
    c.execute(text('UPDATE receipt SET result_id=:id WHERE op_id=:op'), {'id':business_id,'op':op})
    return business_id

def counts(c):
    return tuple(c.scalar(text(f'SELECT count(*) FROM {table}')) for table in ('receipt','business','audit'))

def test_pending_lookup_is_absent_and_duplicate_waits_until_commit(proof):
    a=proof.connect(); tx=a.begin(); result=prepare(a)
    with proof.connect() as reader:
        assert reader.scalar(text("SELECT count(*) FROM receipt WHERE op_id='op-a'")) == 0
        reader.execute(text("SET LOCAL lock_timeout='250ms'"))
        with pytest.raises(OperationalError) as exc:
            reader.execute(text("INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES ('op-a','actor-a','site-a','hash-a') ON CONFLICT DO NOTHING"))
        assert exc.value.orig.sqlstate == '55P03'
    tx.commit(); a.close()
    with proof.begin() as c:
        inserted=c.execute(text("INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES ('op-a','actor-a','site-a','hash-a') ON CONFLICT DO NOTHING"))
        assert inserted.rowcount == 0
        assert c.scalar(text("SELECT result_id FROM receipt WHERE op_id='op-a'")) == result
        assert counts(c) == (1,1,1)

def test_rollback_after_audit_flush_leaves_no_receipt_or_mutation(proof):
    with proof.connect() as c:
        tx=c.begin(); prepare(c); assert counts(c)==(1,1,1); tx.rollback()
    with proof.begin() as c:
        assert counts(c)==(0,0,0)
        prepare(c)
        assert counts(c)==(1,1,1)

def test_unique_key_never_overwrites_actor_site_or_fingerprint(proof):
    with proof.begin() as c: prepare(c)
    for actor,site,fp in [('actor-b','site-a','hash-a'),('actor-a','site-b','hash-a'),('actor-a','site-a','hash-b')]:
        with proof.begin() as c:
            result=c.execute(text('INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES (:op,:actor,:site,:fp) ON CONFLICT DO NOTHING'),{'op':'op-a','actor':actor,'site':site,'fp':fp})
            assert result.rowcount==0
            row=c.execute(text("SELECT actor,site,fingerprint FROM receipt WHERE op_id='op-a'")).one()
            assert tuple(row)==('actor-a','site-a','hash-a')
            assert counts(c)==(1,1,1)

def test_committed_receipt_requires_a_real_business_result(proof):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with proof.begin() as c:
            c.execute(text("INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES ('orphan','actor-a','site-a','hash-a')"))
    with proof.connect() as c:
        assert counts(c) == (0, 0, 0)

def test_receipt_result_must_reference_committed_business(proof):
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        with proof.begin() as c:
            c.execute(text("INSERT INTO receipt(op_id,actor,site,fingerprint,result_id) VALUES ('bad','actor-a','site-a','hash-a',999999)"))
    with proof.connect() as c:
        assert counts(c) == (0, 0, 0)

def test_absent_lookup_before_late_original_does_not_fence_it(proof):
    with proof.connect() as reader:
        assert reader.scalar(text("SELECT count(*) FROM receipt WHERE op_id='late'")) == 0
    with proof.begin() as delayed:
        prepare(delayed, op='late')
    with proof.connect() as verify:
        assert counts(verify) == (1, 1, 1)


def test_retry_admitted_first_prevents_late_same_key_second_insert(proof):
    with proof.connect() as reader:
        assert reader.scalar(text("SELECT count(*) FROM receipt WHERE op_id='late'")) == 0
    with proof.begin() as retry:
        first_result = prepare(retry, op='late')
    with proof.begin() as delayed:
        row = delayed.execute(text("INSERT INTO receipt(op_id,actor,site,fingerprint) VALUES ('late','actor-a','site-a','hash-a') ON CONFLICT DO NOTHING"))
        assert row.rowcount == 0
        assert delayed.scalar(text("SELECT result_id FROM receipt WHERE op_id='late'")) == first_result
        assert counts(delayed) == (1, 1, 1)

def test_disconnect_before_commit_rolls_back_experimental_rows(proof):
    c = proof.connect()
    c.begin()
    prepare(c, op='disconnect')
    c.close()
    with proof.connect() as verify:
        assert counts(verify) == (0, 0, 0)
