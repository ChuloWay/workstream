"""Current pre-submit result ordering and metadata schema proof."""



import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.core.identifiers import new_record_id
from tests.test_pre_submit_attempt_recovery import _harness, _reserve


pytestmark = pytest.mark.postgres_schema_contract


@pytest.mark.asyncio
async def test_new_result_rows_require_valid_order_and_bounded_metadata(
    tmp_path,
    isolated_database_env: str,
) -> None:
    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, [])
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            completed = await workflow.execute_reserved(
                harness.request,
                reservation,
                preparation_request=harness.preparation_request,
            )
        retained_id = str(completed.evidence.evidence_set_id)
        new_id = str(new_record_id())
        attempt_id = str(new_record_id())
        packet_sha256 = "sha256:" + "d" * 64
        async with harness.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                await connection.execute(
                    text(
                        "insert into pre_submit_execution_attempts ("
                        "id,idempotency_key,actor_profile_id,identity_link_id,task_id,"
                        "assignment_id,prepared_generation_id,claim_nonce,request_json,"
                        "request_digest,status) select :attempt,:key,e.actor_profile_id,"
                        "e.identity_link_id,e.task_id,e.assignment_id,e.prepared_generation_id,"
                        ":nonce,(to_jsonb(e)||jsonb_build_object('packet_sha256',"
                        "cast(:packet_sha256 as text)))::json,'sha256:'||encode(sha256("
                        "convert_to(project_guide_projection_canonical_json(to_jsonb(e)||"
                        "jsonb_build_object('packet_sha256',cast(:packet_sha256 as text))),"
                        "'UTF8')),'hex'),'reserved' from pre_submit_evidence_sets e "
                        "where e.id=:retained"
                    ),
                    {
                        "attempt": attempt_id,
                        "key": str(new_record_id()),
                        "nonce": str(new_record_id()),
                        "packet_sha256": packet_sha256,
                        "retained": retained_id,
                    },
                )
                await connection.execute(
                    text(
                        "insert into pre_submit_evidence_sets select "
                        "(jsonb_populate_record(null::pre_submit_evidence_sets,to_jsonb(e)||"
                        "jsonb_build_object('id',cast(:new_id as text),'operation_identity',"
                        "'sha256:'||repeat('c',64),'packet_sha256',cast(:packet_sha256 as text),"
                        "'attempt_id',cast(:attempt as text),'attempt_request_digest',"
                        "a.request_digest,'created_at',transaction_timestamp()))).* "
                        "from pre_submit_evidence_sets e join pre_submit_execution_attempts a "
                        "on a.id=:attempt where e.id=:retained"
                    ),
                    {
                        "new_id": new_id,
                        "retained": retained_id,
                        "packet_sha256": packet_sha256,
                        "attempt": attempt_id,
                    },
                )
                await connection.execute(
                    text(
                        "update pre_submit_execution_attempts set status='completed',"
                        "evidence_set_id=:evidence where id=:attempt"
                    ),
                    {"evidence": new_id, "attempt": attempt_id},
                )
                await connection.execute(text("set constraints all immediate"))
                insert_result = text(
                    "insert into pre_submit_evidence_results (id,evidence_set_id,"
                    "result_order,schema_version,dispatch_authority,definition_id,"
                    "definition_version,public_name,source,phase,classification,severity,"
                    "status,message_code,effective_plan_sha256,locked_policy_sha256,"
                    "checker_order,metadata_json) values (:id,:parent,0,'v1',"
                    "'schema-test','test.check','v1','Test check','test','custody',"
                    "'mandatory_integrity','blocking','passed','test.passed',:digest,"
                    ":digest,:checker_order,cast(:metadata as json))"
                )
                parameters = {"parent": new_id, "digest": "sha256:" + "a" * 64}
                invalid = (
                    (None, "[]", "pre-submit result reconstruction fields required"),
                    (-1, "[]", "pre-submit result reconstruction fields required"),
                    (0, None, "pre-submit result reconstruction fields required"),
                    (0, '{"entry_count":1}', "pre-submit result reconstruction fields required"),
                    (0, '[["entry_count",-1]]', "pre-submit result metadata invalid"),
                    (
                        0,
                        '[["entry_count",1],["entry_count",2]]',
                        "pre-submit result metadata invalid",
                    ),
                )
                for checker_order, metadata, expected in invalid:
                    with pytest.raises(DBAPIError, match=expected):
                        async with connection.begin_nested():
                            await connection.execute(
                                insert_result,
                                {
                                    **parameters,
                                    "id": str(new_record_id()),
                                    "checker_order": checker_order,
                                    "metadata": metadata,
                                },
                            )
                await connection.execute(
                    insert_result,
                    {
                        **parameters,
                        "id": str(new_record_id()),
                        "checker_order": 0,
                        "metadata": '[["entry_count",1],["finding_count",0]]',
                    },
                )
                assert (
                    await connection.scalar(
                        text(
                            "select count(*) from pre_submit_evidence_results "
                            "where evidence_set_id=:id and checker_order=0"
                        ),
                        {"id": new_id},
                    )
                    == 1
                )
            finally:
                await transaction.rollback()
    finally:
        await harness.close()


async def test_manifest_metadata_is_hash_bound_on_insert_and_immutable(
    tmp_path, isolated_database_env,
):
    """Real inspected evidence is the valid control for direct storage rejections."""
    import json
    from copy import deepcopy
    from app.core.hashing import canonical_json_hash

    harness = await _harness(tmp_path, isolated_database_env)
    try:
        async with harness.factory() as session:
            workflow = harness.workflow(session, [])
            reservation = await _reserve(workflow, harness.request, harness.preparation_request)
            completed = await workflow.execute_reserved(
                harness.request, reservation, preparation_request=harness.preparation_request,
            )
        evidence_id = str(completed.evidence.evidence_set_id)
        async with harness.factory() as session:
            body, digest = (await session.execute(text(
                "select semantic_manifest_body,semantic_manifest_sha256 "
                "from pre_submit_evidence_sets where id=:id"
            ), {"id": evidence_id})).one()
        assert canonical_json_hash(body) == digest
        from tests.test_submission_manifest import _archive, _manifest
        unicode_manifest = _manifest(_archive([("café/α.txt", b"verified")]))
        malformed = deepcopy(body)
        malformed["entries"][0]["content"] = "not metadata"
        async with harness.factory() as session, session.begin():
            for candidate, commitment, valid in (
                (body, digest, True), (unicode_manifest.as_dict(), unicode_manifest.sha256, True),
                (body, "sha256:" + "f" * 64, False),
                (None, digest, False), (malformed, canonical_json_hash(malformed), False),
            ):
                assert await session.scalar(text(
                    "select public.submission_manifest_metadata_valid(cast(:body as jsonb),:digest)"
                ), {"body": json.dumps(candidate), "digest": commitment}) is valid
            for path in ("../outside.txt", "/absolute.txt", "dir\\file.txt", "a//b", "a/./b", "a./b", "drive:c/file", "cafe\u0301.txt", "x" * 4097):
                candidate = deepcopy(unicode_manifest.as_dict())
                candidate["entries"] = [candidate["entries"][-1]]
                candidate["entries"][0]["normalized_path"] = path
                assert not await session.scalar(text(
                    "select public.submission_manifest_metadata_valid(cast(:body as jsonb),:digest)"
                ), {"body": json.dumps(candidate), "digest": canonical_json_hash(candidate)})
            for candidate, commitment in ((None, digest), (malformed, digest), (body, "sha256:" + "f" * 64)):
                with pytest.raises(DBAPIError, match="pre-submit manifest metadata invalid"):
                    async with session.begin_nested():
                        await session.execute(text(
                            "insert into pre_submit_evidence_sets select "
                            "(jsonb_populate_record(null::pre_submit_evidence_sets,to_jsonb(e)||"
                            "jsonb_build_object('semantic_manifest_body',cast(:body as jsonb),"
                            "'semantic_manifest_sha256',cast(:digest as text),'created_at',transaction_timestamp()))).* "
                            "from pre_submit_evidence_sets e where e.id=:id"
                        ), {"body": json.dumps(candidate), "digest": commitment, "id": evidence_id})
            with pytest.raises(DBAPIError, match="immutable"):
                async with session.begin_nested():
                    await session.execute(text(
                        "update pre_submit_evidence_sets set semantic_manifest_body=null where id=:id"
                    ), {"id": evidence_id})
            assert await session.scalar(text(
                "select semantic_manifest_body from pre_submit_evidence_sets where id=:id"
            ), {"id": evidence_id}) == body
    finally:
        await harness.close()


async def test_manifest_upgrade_preserves_old_evidence_without_inventing_metadata(
    tmp_path, isolated_database_env, migration_lock,
):
    import asyncio
    import asyncpg
    from alembic import command
    from app.db import session as db_session
    from app.modules.artifacts.pre_submit_evidence import PreSubmitEvidenceConflict
    from tests.migration_fixtures import (
        _config, add_current_art_seed_column, restore_predecessor_evidence_schema,
    )

    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0020_review_admission_lock_order")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        harness = await _harness(tmp_path, isolated_database_env)
        try:
            calls = []
            async with harness.factory() as session:
                workflow = harness.workflow(session, calls)
                reservation = await _reserve(workflow, harness.request, harness.preparation_request)
                completed = await workflow.execute_reserved(
                    harness.request, reservation, preparation_request=harness.preparation_request,
                )
            evidence_id = str(completed.evidence.evidence_set_id)
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with harness.factory() as session:
                before = await session.scalar(text(
                    "select to_jsonb(e) from pre_submit_evidence_sets e where id=:id"
                ), {"id": evidence_id})
            await asyncio.to_thread(command.upgrade, _config(), "head")
            async with harness.factory() as session:
                after = await session.scalar(text(
                    "select to_jsonb(e) from pre_submit_evidence_sets e where id=:id"
                ), {"id": evidence_id})
            assert after.pop("semantic_manifest_body") is None
            assert after == before
            async with harness.factory() as session:
                workflow = harness.workflow(session, calls)
                with pytest.raises(PreSubmitEvidenceConflict, match="pre_submit_attempt_manifest_invalid"):
                    await _reserve(workflow, harness.request, harness.preparation_request)
            assert calls == [1]
        finally:
            await harness.close()


async def test_upgraded_consumed_admission_without_metadata_is_unavailable(
    tmp_path, isolated_database_env, migration_lock,
):
    """Real retained admission recovery denies without rewriting its consumed facts."""
    import asyncio
    import asyncpg
    from alembic import command
    from app.db import session as db_session
    from app.modules.artifacts.api import SubmissionAdmissionConsumptionError
    from app.modules.checkers.api import SubmissionPacketView
    from app.modules.artifacts.submission_bindings import SubmissionAdmissionConsumptionService
    from tests.migration_fixtures import (
        _config, add_current_art_seed_column, restore_predecessor_evidence_schema,
    )
    from tests.historical_submission_fixtures import historical_material_fixture
    from app.modules.artifacts.api.submission_admission import ConsumedSubmissionAdmissionRequest
    from tests.test_artifact_bindings import _Allow

    with migration_lock():
        await db_session.dispose_engine()
        connection = await asyncpg.connect(isolated_database_env.replace("+asyncpg", ""))
        try:
            await connection.execute("drop schema public cascade; create schema public")
        finally:
            await connection.close()
        await asyncio.to_thread(command.upgrade, _config(), "0020_review_admission_lock_order")
        original_columns = await add_current_art_seed_column(isolated_database_env)
        async with historical_material_fixture(tmp_path, isolated_database_env) as h:
            request = ConsumedSubmissionAdmissionRequest(
                admission_id=h.created.admission_id, project_id=h.request.project_id,
                task_id=h.request.task_id, assignment_id=h.request.assignment_id,
                contributor_id=h.facts.contributor_id, submission_id=h.created.submission_id,
                submission_version=h.created.submission_version,
                packet_sha256=SubmissionPacketView(h.creation_request.summary, h.creation_request.contributor_attestation).sha256,
            )
            await restore_predecessor_evidence_schema(isolated_database_env, original_columns)
            async with h.factory() as session:
                before = await session.scalar(text(
                    "select to_jsonb(a) from submission_bundle_admissions a where id=:id"
                ), {"id": str(request.admission_id)})
                bindings = await session.scalar(text("select count(*) from artifact_bindings"))
            await asyncio.to_thread(command.upgrade, _config(), "head")
            authority = _Allow()
            async with h.factory() as session, session.begin():
                with pytest.raises(SubmissionAdmissionConsumptionError, match="submission_bundle_admission_unavailable"):
                    await SubmissionAdmissionConsumptionService(session, authority).read_consumed(request)
                assert await session.scalar(text(
                    "select to_jsonb(a) from submission_bundle_admissions a where id=:id"
                ), {"id": str(request.admission_id)}) == before
                assert await session.scalar(text("select count(*) from artifact_bindings")) == bindings
            authority.consume.assert_not_awaited()
            assert h.store.opens == []


async def _create_manifest_insert_probe(connection):
    """Use the real column types and INSERT guard without unrelated parent constraints."""
    await connection.execute(
        'CREATE TEMP TABLE manifest_insert_probe AS SELECT semantic_manifest_body, '
        'semantic_manifest_sha256 FROM public.pre_submit_evidence_sets WITH NO DATA'
    )
    await connection.execute(
        'CREATE TRIGGER manifest_probe BEFORE INSERT ON manifest_insert_probe '
        'FOR EACH ROW EXECUTE FUNCTION public.guard_submission_manifest_metadata()'
    )


async def test_native_json_insert_recovers_the_validated_numeric_representation(isolated_database_env):
    import asyncpg
    import json
    from app.modules.artifacts.submission_manifest import SubmissionManifest
    from app.core.hashing import canonical_json_hash
    from tests.test_submission_manifest import _archive, _manifest

    connection = await asyncpg.connect(isolated_database_env.replace('+asyncpg', ''))
    try:
        await _create_manifest_insert_probe(connection)
        for count, literal in ((1, '1'), (1, '1e0'), (10, '1e1')):
            manifest = _manifest(_archive([('a', b'x' * count)]))
            native_json = json.dumps(manifest.as_dict()).replace(f'"byte_count": {count}', f'"byte_count": {literal}')
            assert f'"byte_count": {literal}' in native_json
            if 'e' in literal:
                assert type(json.loads(native_json)['entries'][0]['byte_count']) is float
            stored = await connection.fetchval(
                'INSERT INTO manifest_insert_probe VALUES ($1::json,$2) RETURNING semantic_manifest_body',
                native_json, manifest.sha256,
            )
            recovered = json.loads(stored)
            assert type(recovered['entries'][0]['byte_count']) is int
            assert SubmissionManifest.from_dict(recovered, sha256=manifest.sha256) == manifest
        for literal in ('1.0', '1.5'):
            manifest = _manifest(_archive([('a', b'x')]))
            native_json = json.dumps(manifest.as_dict()).replace('"byte_count": 1', f'"byte_count": {literal}')
            with pytest.raises(asyncpg.CheckViolationError, match='pre-submit manifest metadata invalid'):
                await connection.execute('INSERT INTO manifest_insert_probe VALUES ($1::json,$2)', native_json, canonical_json_hash(json.loads(native_json)))
    finally:
        await connection.close()


async def test_manifest_insert_guard_rejects_hash_consistent_inventory_collisions(isolated_database_env):
    import asyncpg
    import json
    from app.core.hashing import canonical_json_hash
    from tests.test_submission_manifest import _archive, _manifest

    connection = await asyncpg.connect(isolated_database_env.replace('+asyncpg', ''))
    try:
        await _create_manifest_insert_probe(connection)
        valid = _manifest(_archive([('café/a', b'x'), ('cafe', b'x')]))
        await connection.execute('INSERT INTO manifest_insert_probe VALUES ($1::json,$2)', json.dumps(valid.as_dict()), valid.sha256)
        template = _manifest(_archive([('safe', b'x')])).as_dict()
        entry = template['entries'][0]
        for paths in (('A', 'a'), ('dir', 'dir/x'), ('DIR/x', 'dir'), ('STRASSE', 'Straße'), ('Σ', 'ς'), ('İ', 'i\u0307')):
            body = dict(template, entries=sorted([dict(entry, normalized_path=path) for path in paths], key=lambda item: item['normalized_path']))
            with pytest.raises(asyncpg.CheckViolationError, match='pre-submit manifest metadata invalid'):
                await connection.execute('INSERT INTO manifest_insert_probe VALUES ($1::json,$2)', json.dumps(body), canonical_json_hash(body))
        assert await connection.fetchval('SELECT count(*) FROM manifest_insert_probe') == 1
    finally:
        await connection.close()


async def test_database_casefold_matches_frozen_unicode_15(isolated_database_env):
    import asyncpg
    import hashlib
    import importlib.util
    import json
    from pathlib import Path
    import unicodedata

    spec = importlib.util.spec_from_file_location('manifest_migration', Path(__file__).parents[1] / 'alembic/versions/0021_submission_manifest.py')
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    mapping = json.loads(migration._UNICODE_15_CASEFOLD_JSON)
    assert unicodedata.unidata_version == '15.0.0'
    assert len(mapping) == 1530
    assert hashlib.sha256(migration._UNICODE_15_CASEFOLD_JSON.encode()).hexdigest() == 'c0d6e0ca212805674e7443c1212d732e11fb9faf16d92326aa1a9536caadbf3a'
    expected = {chr(i): chr(i).casefold() for i in range(0x110000) if chr(i).casefold() != chr(i)}
    assert mapping == expected
    connection = await asyncpg.connect(isolated_database_env.replace('+asyncpg', ''))
    try:
        values = list(mapping) + ['', 'café/cafe', 'dir/file', '123', '中', '🙂', 'Straße/İΣ']
        observed = await connection.fetch(
            'SELECT value,public.submission_archive_casefold(value) AS folded FROM unnest($1::text[]) AS values(value)', values,
        )
        assert [(row['value'], row['folded']) for row in observed] == [(value, value.casefold()) for value in values]
    finally:
        await connection.close()
