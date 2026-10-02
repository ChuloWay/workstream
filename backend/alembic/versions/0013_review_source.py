"""Immutable Review source storage without activating decision authority."""

from alembic import op

revision = "0013_review_source"
down_revision = "0012_review_packet"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = pg_catalog, public, pg_temp")
    op.execute("""
CREATE TABLE public.reviews (
	id UUID NOT NULL,
	project_id UUID NOT NULL,
	task_id UUID NOT NULL,
	task_assignment_id UUID NOT NULL,
	submission_id UUID NOT NULL,
	review_queue_entry_id UUID NOT NULL,
	review_lease_id UUID NOT NULL,
	packet_manifest_id UUID NOT NULL,
	reviewer_id UUID NOT NULL,
	reviewer_contribution_policy_version_id UUID NOT NULL,
	locked_review_policy_id UUID NOT NULL,
	submission_version INTEGER NOT NULL,
	packet_manifest_digest VARCHAR(71) NOT NULL,
	artifact_hash VARCHAR(71) NOT NULL,
	locked_guide_version VARCHAR(50) NOT NULL,
	locked_review_policy_generation INTEGER NOT NULL,
	locked_review_policy_hash VARCHAR(71) NOT NULL,
	predecessor_review_id UUID,
	decision VARCHAR(20) NOT NULL,
	summary VARCHAR(4000) NOT NULL,
	finding_count INTEGER NOT NULL,
	blocking_finding_count INTEGER NOT NULL,
	resolution_count INTEGER NOT NULL,
	aggregate_digest VARCHAR(71) NOT NULL,
	completed_at TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp() NOT NULL,
	CONSTRAINT pk_reviews PRIMARY KEY (id),
	CONSTRAINT ck_reviews_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_reviews_submission_id UNIQUE (submission_id),
	CONSTRAINT uq_reviews_review_lease_id UNIQUE (review_lease_id),
	CONSTRAINT uq_reviews_packet_manifest_id UNIQUE (packet_manifest_id),
	CONSTRAINT uq_reviews_predecessor_review_id UNIQUE (predecessor_review_id),
	CONSTRAINT ck_reviews_decision CHECK (decision in ('accept','needs_revision','reject')),
	CONSTRAINT ck_reviews_summary CHECK (length(btrim(summary)) between 1 and 4000 and summary ~ '[^[:space:]]'),
	CONSTRAINT ck_reviews_positive_versions CHECK (submission_version > 0 and locked_review_policy_generation > 0),
	CONSTRAINT ck_reviews_counts CHECK (finding_count between 0 and 100 and blocking_finding_count between 0 and finding_count and resolution_count between 0 and 100),
	CONSTRAINT ck_reviews_guide_version CHECK (length(btrim(locked_guide_version)) > 0),
	CONSTRAINT ck_reviews_aggregate_digest CHECK (aggregate_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_reviews_packet_manifest_digest CHECK (packet_manifest_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_reviews_artifact_hash CHECK (artifact_hash ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT ck_reviews_locked_review_policy_hash CHECK (locked_review_policy_hash ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT fk_reviews_project_id_projects FOREIGN KEY(project_id) REFERENCES public.projects (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_task_id_workstream_tasks FOREIGN KEY(task_id) REFERENCES public.workstream_tasks (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_task_assignment_id_task_assignments FOREIGN KEY(task_assignment_id) REFERENCES public.task_assignments (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_submission_id_submissions FOREIGN KEY(submission_id) REFERENCES public.submissions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_review_queue_entry_id_review_queue_entries FOREIGN KEY(review_queue_entry_id) REFERENCES public.review_queue_entries (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_review_lease_id_review_leases FOREIGN KEY(review_lease_id) REFERENCES public.review_leases (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_packet_manifest_id_review_packet_manifests FOREIGN KEY(packet_manifest_id) REFERENCES public.review_packet_manifests (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_reviewer_id_actor_profiles FOREIGN KEY(reviewer_id) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_reviewer_contribution_policy_version_id_cont_a7f1 FOREIGN KEY(reviewer_contribution_policy_version_id) REFERENCES public.contribution_policy_versions (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_locked_review_policy_id_review_policies FOREIGN KEY(locked_review_policy_id) REFERENCES public.review_policies (id) ON DELETE RESTRICT,
	CONSTRAINT fk_reviews_predecessor_review_id_reviews FOREIGN KEY(predecessor_review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE public.review_findings (
	id UUID NOT NULL,
	review_id UUID NOT NULL,
	item_order INTEGER NOT NULL,
	finding_kind VARCHAR(16) NOT NULL,
	area VARCHAR(200) NOT NULL,
	issue VARCHAR(4000) NOT NULL,
	required_fix VARCHAR(4000) NOT NULL,
	CONSTRAINT pk_review_findings PRIMARY KEY (id),
	CONSTRAINT ck_review_findings_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_review_findings_review_id UNIQUE (review_id, item_order),
	CONSTRAINT ck_review_findings_order CHECK (item_order between 0 and 99),
	CONSTRAINT ck_review_findings_kind CHECK (finding_kind in ('blocking','advisory')),
	CONSTRAINT ck_review_findings_area CHECK (length(btrim(area)) between 1 and 200 and area ~ '[^[:space:]]'),
	CONSTRAINT ck_review_findings_issue CHECK (length(btrim(issue)) between 1 and 4000 and issue ~ '[^[:space:]]'),
	CONSTRAINT ck_review_findings_required_fix CHECK (length(btrim(required_fix)) between 1 and 4000 and required_fix ~ '[^[:space:]]'),
	CONSTRAINT fk_review_findings_review_id_reviews FOREIGN KEY(review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE public.finding_resolutions (
	id UUID NOT NULL,
	review_id UUID NOT NULL,
	finding_id UUID NOT NULL,
	item_order INTEGER NOT NULL,
	result VARCHAR(20) NOT NULL,
	rationale VARCHAR(4000) NOT NULL,
	CONSTRAINT pk_finding_resolutions PRIMARY KEY (id),
	CONSTRAINT ck_finding_resolutions_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_finding_resolutions_review_id UNIQUE (review_id, item_order),
	CONSTRAINT uq_finding_resolution_source UNIQUE (review_id, finding_id),
	CONSTRAINT ck_finding_resolutions_order CHECK (item_order between 0 and 99),
	CONSTRAINT ck_finding_resolutions_result CHECK (result in ('resolved','unresolved','not_applicable')),
	CONSTRAINT ck_finding_resolutions_rationale CHECK (length(btrim(rationale)) between 1 and 4000 and rationale ~ '[^[:space:]]'),
	CONSTRAINT fk_finding_resolutions_review_id_reviews FOREIGN KEY(review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT,
	CONSTRAINT fk_finding_resolutions_finding_id_review_findings FOREIGN KEY(finding_id) REFERENCES public.review_findings (id) ON DELETE RESTRICT
)
""")
    op.execute("""
CREATE TABLE public.review_decision_requests (
	id UUID NOT NULL,
	operation_id UUID NOT NULL,
	project_id UUID NOT NULL,
	reviewer_id UUID NOT NULL,
	idempotency_key UUID NOT NULL,
	review_id UUID NOT NULL,
	request_digest VARCHAR(71) NOT NULL,
	CONSTRAINT pk_review_decision_requests PRIMARY KEY (id),
	CONSTRAINT ck_review_decision_requests_id_uuid7 CHECK ((get_byte(uuid_send(id), 6) >> 4) = 7 and (get_byte(uuid_send(id), 8) & 192) = 128),
	CONSTRAINT uq_review_decision_requests_project_id UNIQUE (project_id, reviewer_id, idempotency_key),
	CONSTRAINT uq_review_decision_requests_operation_id UNIQUE (operation_id),
	CONSTRAINT uq_review_decision_requests_review_id UNIQUE (review_id),
	CONSTRAINT ck_review_decision_requests_request_digest CHECK (request_digest ~ '^sha256:[0-9a-f]{64}$'),
	CONSTRAINT fk_review_decision_requests_project_id_projects FOREIGN KEY(project_id) REFERENCES public.projects (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_decision_requests_reviewer_id_actor_profiles FOREIGN KEY(reviewer_id) REFERENCES public.actor_profiles (id) ON DELETE RESTRICT,
	CONSTRAINT fk_review_decision_requests_review_id_reviews FOREIGN KEY(review_id) REFERENCES public.reviews (id) ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
)
""")
    op.execute("""
CREATE FUNCTION public.guard_review_source_creation() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE lease_row public.review_leases%rowtype; queue_row public.review_queue_entries%rowtype;
BEGIN
    SELECT * INTO lease_row FROM public.review_leases
      WHERE id=NEW.review_lease_id AND project_id=NEW.project_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review source lease unavailable' USING ERRCODE='23514';
    END IF;
    SELECT * INTO queue_row FROM public.review_queue_entries
      WHERE id=lease_row.review_queue_entry_id AND project_id=NEW.project_id FOR UPDATE;
    IF NOT FOUND OR lease_row.status<>'active'
       OR lease_row.expires_at<=pg_catalog.clock_timestamp()
       OR queue_row.queue_state<>'leased'
       OR queue_row.active_lease_id IS DISTINCT FROM lease_row.id THEN
        RAISE EXCEPTION 'review source requires active unexpired lease' USING ERRCODE='23514';
    END IF;
    PERFORM 1 FROM public.workstream_tasks
      WHERE id=NEW.task_id AND project_id=NEW.project_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review source task unavailable' USING ERRCODE='23514';
    END IF;
    NEW.completed_at := pg_catalog.clock_timestamp();
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER review_source_creation BEFORE INSERT ON public.reviews
FOR EACH ROW EXECUTE FUNCTION public.guard_review_source_creation();
""")
    op.execute("""
CREATE FUNCTION public.review_source_payload(review_uuid uuid, request_identity boolean)
RETURNS jsonb LANGUAGE sql STABLE SET search_path=pg_catalog,public,pg_temp AS $$
SELECT (pg_catalog.to_jsonb(r)-'completed_at'-'aggregate_digest'
        || pg_catalog.jsonb_build_object(
            'findings',COALESCE((SELECT pg_catalog.jsonb_agg(
                (pg_catalog.to_jsonb(f)-'review_id'-'item_order')
                  - CASE WHEN request_identity THEN ARRAY['id'] ELSE ARRAY[]::text[] END
                ORDER BY f.item_order) FROM public.review_findings f WHERE f.review_id=r.id),'[]'::jsonb),
            'resolutions',COALESCE((SELECT pg_catalog.jsonb_agg(
                (pg_catalog.to_jsonb(x)-'review_id'-'item_order')
                  - CASE WHEN request_identity THEN ARRAY['id'] ELSE ARRAY[]::text[] END
                ORDER BY x.item_order) FROM public.finding_resolutions x WHERE x.review_id=r.id),'[]'::jsonb)))
       - CASE WHEN request_identity THEN ARRAY['id'] ELSE ARRAY[]::text[] END
       || CASE WHEN request_identity
            THEN pg_catalog.jsonb_build_object('domain','workstream.review_decision_request.v0.1','action','review.decision')
            ELSE pg_catalog.jsonb_build_object('domain','workstream.review_source.v0.1') END
FROM public.reviews r WHERE r.id=review_uuid
$$;
""")
    op.execute("""
CREATE FUNCTION public.validate_review_source(review_uuid uuid) RETURNS void
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
DECLARE
    r public.reviews%rowtype; request_row public.review_decision_requests%rowtype;
    source public.submissions%rowtype; ancestor public.submissions%rowtype;
    next_submission uuid; ancestor_review uuid; nearest_review uuid;
    prior_reviews uuid[] := ARRAY[]::uuid[]; open_findings uuid[]; open_blockers uuid[];
    last_version integer; finding_total integer; blocking_total integer;
    resolution_total integer; unresolved_total integer; body jsonb;
BEGIN
    SELECT * INTO r FROM public.reviews WHERE id=review_uuid FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'review source parent unavailable' USING ERRCODE='23514';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM public.review_leases l
      JOIN public.review_queue_entries q ON q.id=l.review_queue_entry_id
      JOIN public.review_packet_manifests p ON p.id=r.packet_manifest_id
      JOIN public.submissions s ON s.id=r.submission_id
      JOIN public.task_assignments a ON a.id=s.task_assignment_id
      JOIN public.actor_profiles actor ON actor.id=r.reviewer_id
      JOIN public.review_policies policy ON policy.id=s.locked_review_policy_id
      JOIN public.artifact_bindings binding ON binding.id=p.submission_binding_id
      JOIN public.artifact_contents content ON content.id=binding.content_id
      WHERE l.id=r.review_lease_id AND l.project_id=r.project_id
        AND l.task_id=r.task_id AND l.submission_id=r.submission_id
        AND l.submission_version=r.submission_version AND l.reviewer_id=r.reviewer_id
        AND l.reviewer_contribution_policy_version_id=r.reviewer_contribution_policy_version_id
        AND l.reviewer_contribution_policy_version_id=s.contribution_policy_version_id
        AND l.status='consumed' AND l.close_reason='review_recorded'
        AND l.claimed_at<=r.completed_at AND r.completed_at<l.expires_at
        AND l.closed_at>=r.completed_at
        AND q.id=r.review_queue_entry_id AND q.project_id=r.project_id
        AND q.task_id=r.task_id AND q.submission_id=r.submission_id
        AND q.queue_state='closed' AND q.closed_reason='review_recorded' AND q.active_lease_id IS NULL
        AND p.review_lease_id=l.id AND p.review_queue_entry_id=q.id
        AND p.project_id=r.project_id AND p.task_id=r.task_id
        AND p.submission_id=r.submission_id AND p.submission_version=r.submission_version
        AND p.packet_manifest_digest=r.packet_manifest_digest
        AND s.task_id=r.task_id AND s.version=r.submission_version
        AND s.task_assignment_id=r.task_assignment_id
        AND s.locked_guide_version=r.locked_guide_version
        AND s.locked_review_policy_id=r.locked_review_policy_id
        AND s.locked_review_policy_generation=r.locked_review_policy_generation
        AND s.locked_review_policy_hash=r.locked_review_policy_hash
        AND a.task_id=r.task_id AND a.project_id=r.project_id AND a.contributor_id=s.contributor_id
        AND actor.actor_kind='human' AND r.reviewer_id<>s.contributor_id
        AND policy.project_id=r.project_id AND policy.guide_version=r.locked_guide_version
        AND policy.policy_generation=r.locked_review_policy_generation
        AND policy.policy_hash=r.locked_review_policy_hash AND policy.semantics_status='complete'
        AND policy.human_review_required IS TRUE
        AND binding.id=s.artifact_binding_id AND content.id=s.artifact_content_id
        AND r.artifact_hash=content.sha256
    ) THEN
        RAISE EXCEPTION 'review source canonical ownership mismatch' USING ERRCODE='23514';
    END IF;
    SELECT * INTO source FROM public.submissions WHERE id=r.submission_id;
    next_submission:=source.supersedes_submission_id;
    last_version:=source.version;
    WHILE next_submission IS NOT NULL LOOP
        SELECT * INTO ancestor FROM public.submissions WHERE id=next_submission;
        IF NOT FOUND OR ancestor.task_id<>r.task_id OR ancestor.version>=last_version THEN
            RAISE EXCEPTION 'review source submission ancestry mismatch' USING ERRCODE='23514';
        END IF;
        SELECT id INTO ancestor_review FROM public.reviews WHERE submission_id=ancestor.id;
        IF FOUND THEN
            IF nearest_review IS NULL THEN nearest_review:=ancestor_review; END IF;
            prior_reviews:=pg_catalog.array_append(prior_reviews,ancestor_review);
        END IF;
        next_submission:=ancestor.supersedes_submission_id;
        last_version:=ancestor.version;
    END LOOP;
    IF r.predecessor_review_id IS DISTINCT FROM nearest_review OR
       (nearest_review IS NOT NULL AND NOT EXISTS (
          SELECT 1 FROM public.reviews prior WHERE prior.id=nearest_review AND prior.decision='needs_revision'
       )) THEN
        RAISE EXCEPTION 'review source predecessor mismatch' USING ERRCODE='23514';
    END IF;
    SELECT COALESCE(pg_catalog.array_agg(f.id),ARRAY[]::uuid[]),
           COALESCE(pg_catalog.array_agg(f.id) FILTER (WHERE f.finding_kind='blocking'),ARRAY[]::uuid[])
      INTO open_findings,open_blockers FROM public.review_findings f
      WHERE f.review_id=ANY(prior_reviews) AND NOT EXISTS (
        SELECT 1 FROM public.finding_resolutions x
        WHERE x.finding_id=f.id AND x.review_id=ANY(prior_reviews) AND x.result IN ('resolved','not_applicable')
      );
    IF EXISTS (SELECT 1 FROM public.finding_resolutions x WHERE x.review_id=r.id
               AND NOT (x.finding_id=ANY(open_findings)))
       OR EXISTS (SELECT 1 FROM pg_catalog.unnest(open_blockers) AS required(finding_id) WHERE NOT EXISTS (
            SELECT 1 FROM public.finding_resolutions x WHERE x.review_id=r.id AND x.finding_id=required.finding_id
       )) THEN
        RAISE EXCEPTION 'review source finding ancestry or completeness mismatch' USING ERRCODE='23514';
    END IF;
    SELECT count(*),count(*) FILTER (WHERE finding_kind='blocking')
      INTO finding_total,blocking_total FROM public.review_findings WHERE review_id=r.id;
    SELECT count(*),count(*) FILTER (WHERE result='unresolved' AND finding_id=ANY(open_blockers))
      INTO resolution_total,unresolved_total FROM public.finding_resolutions WHERE review_id=r.id;
    IF (r.finding_count,r.blocking_finding_count,r.resolution_count)
       IS DISTINCT FROM (finding_total,blocking_total,resolution_total)
       OR EXISTS (SELECT 1 FROM public.review_findings WHERE review_id=r.id AND item_order>=finding_total)
       OR EXISTS (SELECT 1 FROM public.finding_resolutions WHERE review_id=r.id AND item_order>=resolution_total) THEN
        RAISE EXCEPTION 'review source child counts or order mismatch' USING ERRCODE='23514';
    END IF;
    IF (r.decision='accept' AND blocking_total+unresolved_total<>0)
       OR (r.decision='needs_revision' AND blocking_total+unresolved_total=0)
       OR blocking_total+unresolved_total>100 THEN
        RAISE EXCEPTION 'review source blocking findings incompatible with decision' USING ERRCODE='23514';
    END IF;
    body:=public.review_source_payload(r.id,false);
    IF r.aggregate_digest IS DISTINCT FROM ('sha256:' || pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(public.project_guide_projection_canonical_json(body),'UTF8')),'hex')) THEN
        RAISE EXCEPTION 'review source aggregate digest mismatch' USING ERRCODE='23514';
    END IF;
    SELECT * INTO request_row FROM public.review_decision_requests WHERE review_id=r.id;
    IF NOT FOUND OR (request_row.project_id,request_row.reviewer_id) IS DISTINCT FROM (r.project_id,r.reviewer_id) THEN
        RAISE EXCEPTION 'review source completed request mismatch' USING ERRCODE='23514';
    END IF;
    body:=public.review_source_payload(r.id,true);
    IF request_row.request_digest IS DISTINCT FROM ('sha256:' || pg_catalog.encode(pg_catalog.sha256(
       pg_catalog.convert_to(public.project_guide_projection_canonical_json(body),'UTF8')),'hex')) THEN
        RAISE EXCEPTION 'review source request digest mismatch' USING ERRCODE='23514';
    END IF;
END $$;
""")
    op.execute("""
CREATE FUNCTION public.guard_review_source_aggregate() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF TG_TABLE_NAME='reviews' THEN
        PERFORM public.validate_review_source(NEW.id);
    ELSE
        PERFORM public.validate_review_source(NEW.review_id);
    END IF;
    RETURN NEW;
END $$;
""")
    for table in ("reviews", "review_findings", "finding_resolutions", "review_decision_requests"):
        op.execute(f"""
CREATE CONSTRAINT TRIGGER {table}_aggregate AFTER INSERT ON public.{table}
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.guard_review_source_aggregate();
""")
        op.execute(f"""
CREATE TRIGGER {table}_immutable BEFORE UPDATE OR DELETE OR TRUNCATE ON public.{table}
FOR EACH STATEMENT EXECUTE FUNCTION public.reject_artifact_fact_mutation();
""")

    op.execute("""
CREATE FUNCTION public.guard_review_source_closed_queue() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog,public,pg_temp AS $$
BEGIN
    IF OLD.queue_state='closed'
       AND (NEW.queue_state,NEW.closed_reason,NEW.closed_at,NEW.active_lease_id) IS DISTINCT FROM
           (OLD.queue_state,OLD.closed_reason,OLD.closed_at,OLD.active_lease_id)
       AND EXISTS (SELECT 1 FROM public.reviews r WHERE r.review_queue_entry_id=OLD.id) THEN
        RAISE EXCEPTION 'recorded review queue closure is immutable' USING ERRCODE='55000';
    END IF;
    RETURN NEW;
END $$;
""")
    op.execute("""
CREATE TRIGGER review_source_closed_queue BEFORE UPDATE ON public.review_queue_entries
FOR EACH ROW EXECUTE FUNCTION public.guard_review_source_closed_queue();
""")


def downgrade() -> None:
    raise RuntimeError("Workstream v0.1 migrations cannot be downgraded; recreate the database")
