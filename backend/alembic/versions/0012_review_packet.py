"""Persist immutable normalized reviewer packets without activating review access."""

from alembic import op

revision = "0012_review_packet"
down_revision = "0011_task_routing_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute("""
CREATE TABLE public.review_packet_manifests (
	id UUID NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	review_lease_id UUID NOT NULL,
	review_queue_entry_id UUID NOT NULL,
	packet_manifest_generation INTEGER NOT NULL,
	packet_manifest_digest VARCHAR(71) NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	submission_id UUID NOT NULL,
	submission_version INTEGER NOT NULL,
	checker_run_id UUID NOT NULL,
	result_id UUID NOT NULL,
	guide_id UUID NOT NULL,
	guide_version VARCHAR(50) NOT NULL,
	source_snapshot_id UUID NOT NULL,
	project_setup_run_id UUID NOT NULL,
	setup_generation INTEGER NOT NULL,
	submission_binding_id UUID NOT NULL,
	submission_logical_role VARCHAR(32) NOT NULL,
	submission_media_type VARCHAR(100) NOT NULL,
	CONSTRAINT pk_review_packet_manifests PRIMARY KEY (id),
	CONSTRAINT ck_review_packet_manifests_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_review_packet_lease UNIQUE (review_lease_id),
	CONSTRAINT fk_review_packet_task FOREIGN KEY(task_id, project_id) REFERENCES public.workstream_tasks (id, project_id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_submission FOREIGN KEY(submission_id, task_id, submission_version) REFERENCES public.submissions (id, task_id, version) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_checker FOREIGN KEY(checker_run_id, task_id, submission_id) REFERENCES public.checker_runs (id, task_id, submission_id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_snapshot FOREIGN KEY(source_snapshot_id, project_id, guide_id) REFERENCES public.guide_source_snapshots (id, project_id, guide_id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_setup FOREIGN KEY(project_setup_run_id, project_id, guide_id, source_snapshot_id, setup_generation) REFERENCES public.project_setup_runs (id, project_id, guide_id, source_snapshot_id, setup_generation) ON DELETE RESTRICT,
	CONSTRAINT ck_review_packet_manifests_positive_generations CHECK (submission_version > 0 and setup_generation > 0 and packet_manifest_generation > 0),
	CONSTRAINT ck_review_packet_manifests_guide_version_nonblank CHECK (length(btrim(guide_version)) > 0),
	CONSTRAINT ck_review_packet_manifests_digest_shape CHECK (packet_manifest_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_review_packet_manifests_original_zip CHECK (submission_logical_role='submission_bundle_original' and submission_media_type='application/zip'),
	CONSTRAINT fk_review_packet_manifests_review_lease_id_review_leases FOREIGN KEY(review_lease_id) REFERENCES public.review_leases (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_manifests_review_queue_entry_id_review_cc56 FOREIGN KEY(review_queue_entry_id) REFERENCES public.review_queue_entries (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_manifests_result_id_checker_runs FOREIGN KEY(result_id) REFERENCES public.checker_runs (result_id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_manifests_guide_id_project_guides FOREIGN KEY(guide_id) REFERENCES public.project_guides (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_manifests_submission_binding_id_artifa_4ee3 FOREIGN KEY(submission_binding_id) REFERENCES public.artifact_bindings (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE public.review_packet_guide_items (
	packet_id UUID NOT NULL,
	source_item_id UUID NOT NULL,
	ingest_id UUID NOT NULL,
	item_order INTEGER NOT NULL,
	logical_role VARCHAR(32) NOT NULL,
	media_type VARCHAR(100) NOT NULL,
	CONSTRAINT pk_review_packet_guide_items PRIMARY KEY (packet_id, source_item_id),
	CONSTRAINT uq_review_packet_ingest UNIQUE (packet_id, ingest_id),
	CONSTRAINT uq_review_packet_order UNIQUE (packet_id, item_order),
	CONSTRAINT ck_review_packet_guide_items_order_nonnegative CHECK (item_order >= 0),
	CONSTRAINT ck_review_packet_guide_items_original_guide CHECK (logical_role='guide_source_original'),
	CONSTRAINT ck_review_packet_guide_items_guide_media CHECK (media_type in ('application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document','application/vnd.openxmlformats-officedocument.presentationml.presentation')),
	CONSTRAINT fk_review_packet_guide_items_packet_id_review_packet_manifests FOREIGN KEY(packet_id) REFERENCES public.review_packet_manifests (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_guide_items_source_item_id_guide_sourc_211e FOREIGN KEY(source_item_id) REFERENCES public.guide_source_snapshot_items (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_packet_guide_items_ingest_id_guide_source_art_22a8 FOREIGN KEY(ingest_id) REFERENCES public.guide_source_artifact_ingests (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE FUNCTION public.guard_review_packet_creation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE lease_row public.review_leases%rowtype; queue_row public.review_queue_entries%rowtype;
BEGIN
    SELECT * INTO lease_row FROM public.review_leases
      WHERE id=NEW.review_lease_id AND project_id=NEW.project_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review packet lease unavailable' USING ERRCODE='23514';
    END IF;
    SELECT * INTO queue_row FROM public.review_queue_entries
      WHERE id=lease_row.review_queue_entry_id AND project_id=NEW.project_id FOR UPDATE;
    IF NOT FOUND OR lease_row.status <> 'active' OR queue_row.queue_state <> 'leased'
       OR lease_row.expires_at <= pg_catalog.clock_timestamp()
       OR queue_row.active_lease_id IS DISTINCT FROM lease_row.id
       OR (NEW.review_queue_entry_id,NEW.task_id,NEW.submission_id,NEW.submission_version,
           NEW.checker_run_id,NEW.packet_manifest_generation) IS DISTINCT FROM
          (queue_row.id,lease_row.task_id,lease_row.submission_id,lease_row.submission_version,
           queue_row.admitting_checker_run_id,lease_row.attempt_generation)
    THEN
        RAISE EXCEPTION 'review packet requires exact active lease' USING ERRCODE='23514';
    END IF;
    NEW.created_at := pg_catalog.clock_timestamp();
    RETURN NEW;
END $$
""")
    op.execute("""
CREATE TRIGGER review_packet_creation BEFORE INSERT ON public.review_packet_manifests
FOR EACH ROW EXECUTE FUNCTION public.guard_review_packet_creation()
""")
    op.execute("""
CREATE FUNCTION public.validate_review_packet(packet_uuid uuid) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE packet public.review_packet_manifests%rowtype; member_count integer; membership jsonb;
BEGIN
    SELECT * INTO packet FROM public.review_packet_manifests WHERE id=packet_uuid;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review packet parent unavailable' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM public.submissions s
        JOIN public.checker_runs r ON r.id=packet.checker_run_id
        JOIN public.artifact_bindings b ON b.id=s.artifact_binding_id
        JOIN public.artifact_contents c ON c.id=b.content_id
        JOIN public.project_guides g ON g.id=packet.guide_id
        JOIN public.guide_mutation_idempotency_records a ON a.operation_id=g.activation_operation_id
        JOIN public.project_setup_runs setup ON setup.id=packet.project_setup_run_id
        JOIN public.guide_source_snapshots snapshot ON snapshot.id=packet.source_snapshot_id
        WHERE s.id=packet.submission_id AND s.task_id=packet.task_id AND s.version=packet.submission_version
          AND s.locked_guide_version=packet.guide_version
          AND s.locked_guide_source_snapshot_id=packet.source_snapshot_id
          AND s.locked_guide_source_snapshot_hash=snapshot.bundle_hash
          AND r.submission_id=s.id AND r.task_id=s.task_id AND r.submission_version=s.version
          AND r.result_id=packet.result_id AND r.status='completed'
          AND r.routing_recommendation='allow_review'
          AND b.id=packet.submission_binding_id AND b.project_id=packet.project_id
          AND b.resource_type='submission' AND b.resource_id=s.id::text
          AND b.logical_role=packet.submission_logical_role AND b.scope_version=1
          AND c.media_type=packet.submission_media_type
          AND g.project_id=packet.project_id AND g.version=packet.guide_version
          AND g.status IN ('active','superseded')
          AND a.project_id=g.project_id AND a.resource_id=g.id
          AND a.response_json::jsonb #>> '{command,target,proposal,setup_run_id}'=setup.id::text
          AND a.response_json::jsonb #>> '{command,target,proposal,setup_generation}'=setup.setup_generation::text
          AND setup.source_snapshot_id=snapshot.id AND setup.guide_id=g.id
          AND setup.project_id=g.project_id AND setup.guide_version=g.version
          AND snapshot.guide_id=g.id AND snapshot.project_id=g.project_id AND snapshot.guide_version=g.version
    ) THEN
        RAISE EXCEPTION 'review packet canonical header mismatch' USING ERRCODE='23514';
    END IF;
    SELECT count(*) INTO member_count FROM public.review_packet_guide_items WHERE packet_id=packet.id;
    IF member_count NOT BETWEEN 1 AND 100
       OR member_count<>(SELECT count(*) FROM public.guide_source_snapshot_items WHERE source_snapshot_id=packet.source_snapshot_id)
       OR EXISTS (
        SELECT 1 FROM public.review_packet_guide_items m
        LEFT JOIN public.guide_source_snapshot_items item ON item.id=m.source_item_id
        LEFT JOIN public.guide_source_artifact_ingests ingest ON ingest.id=m.ingest_id
        WHERE m.packet_id=packet.id AND (
          item.id IS NULL OR ingest.id IS NULL OR
          (item.source_snapshot_id,item.item_order,item.media_type,item.source_kind,item.ingestion_adapter,
           ingest.source_item_id,ingest.media_type) IS DISTINCT FROM
          (packet.source_snapshot_id,m.item_order,m.media_type,'document','upload',m.source_item_id,m.media_type)
          OR NOT EXISTS (
            SELECT 1 FROM public.artifact_put_attempts put
            JOIN public.artifact_replicas replica ON replica.id=put.replica_id
            JOIN public.artifact_contents content ON content.id=replica.content_id
            WHERE put.guide_source_item_id=item.id AND put.project_id=packet.project_id
              AND put.producer_request_type='guide' AND put.logical_role IS NULL
              AND put.status='object_confirmed'
              AND (put.sha256,put.byte_count,put.media_type)=(ingest.sha256,ingest.byte_count,ingest.media_type)
              AND (content.sha256,content.byte_count,content.media_type)=(ingest.sha256,ingest.byte_count,ingest.media_type)
              AND replica.storage_namespace_id=put.storage_namespace_id
              AND replica.namespace_fingerprint=put.namespace_fingerprint
              AND (
                (put.terminal_result_code='document_stored' AND EXISTS (
                  SELECT 1 FROM public.artifact_operation_receipts receipt
                  WHERE receipt.id=put.receipt_id AND receipt.put_attempt_id=put.id
                    AND receipt.guide_source_item_id=item.id AND receipt.replica_id=replica.id
                    AND receipt.request_digest=put.request_digest AND receipt.provider_object_ref=replica.provider_object_ref
                    AND receipt.outcome='document_stored'
                )) OR
                (put.terminal_result_code='document_stored_observed' AND put.receipt_id IS NULL AND EXISTS (
                  SELECT 1 FROM public.artifact_put_observation_receipts receipt
                  WHERE receipt.put_attempt_id=put.id AND receipt.execution_generation=put.execution_generation
                    AND receipt.outcome='observed_confirmed'
                    AND receipt.expected_sha256=put.sha256 AND receipt.observed_sha256=put.sha256
                    AND receipt.expected_byte_count=put.byte_count AND receipt.observed_byte_count=put.byte_count
                ))
              )
          )
        )
    ) THEN
        RAISE EXCEPTION 'review packet canonical guide membership mismatch' USING ERRCODE='23514';
    END IF;
    SELECT pg_catalog.jsonb_build_object(
      'request',pg_catalog.jsonb_build_object(
        'project_id',packet.project_id,'task_id',packet.task_id,'submission_id',packet.submission_id,
        'submission_version',packet.submission_version,'checker_run_id',packet.checker_run_id,
        'result_id',packet.result_id,'guide_id',packet.guide_id,'guide_version',packet.guide_version,
        'source_snapshot_id',packet.source_snapshot_id,'project_setup_run_id',packet.project_setup_run_id,
        'setup_generation',packet.setup_generation),
      'submission',pg_catalog.jsonb_build_object('binding_id',packet.submission_binding_id,
        'logical_role',packet.submission_logical_role,'media_type',packet.submission_media_type),
      'guide_documents',(SELECT pg_catalog.jsonb_agg(pg_catalog.jsonb_build_object(
        'ingest_id',m.ingest_id,'source_item_id',m.source_item_id,'item_order',m.item_order,
        'logical_role',m.logical_role,'media_type',m.media_type) ORDER BY m.item_order)
        FROM public.review_packet_guide_items m WHERE m.packet_id=packet.id)
    ) INTO membership;
    IF packet.packet_manifest_digest IS DISTINCT FROM ('sha256:' || pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(public.project_guide_projection_canonical_json(membership),'UTF8')),'hex')) THEN
        RAISE EXCEPTION 'review packet semantic digest mismatch' USING ERRCODE='23514';
    END IF;
END $$
""")
    op.execute("""
CREATE FUNCTION public.guard_review_packet_membership() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF TG_TABLE_NAME='review_packet_manifests' THEN
        PERFORM public.validate_review_packet(NEW.id);
    ELSE
        PERFORM public.validate_review_packet(NEW.packet_id);
    END IF;
    RETURN NEW;
END $$
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER review_packet_membership
AFTER INSERT ON public.review_packet_manifests DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.guard_review_packet_membership()
""")
    op.execute("""
CREATE CONSTRAINT TRIGGER review_packet_member_custody
AFTER INSERT ON public.review_packet_guide_items DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION public.guard_review_packet_membership()
""")
    for table in (
        "review_packet_manifests",
        "review_packet_guide_items",
        "guide_source_artifact_ingests",
    ):
        op.execute(f"""
CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{table}
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_artifact_fact_mutation();
""")


def downgrade() -> None:
    """Retained packets and source identities cannot lose custody."""
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
