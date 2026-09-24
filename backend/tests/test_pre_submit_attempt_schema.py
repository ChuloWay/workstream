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
                    (0, None, "pre-submit result metadata invalid"),
                    (0, '{"entry_count":1}', "pre-submit result metadata invalid"),
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
