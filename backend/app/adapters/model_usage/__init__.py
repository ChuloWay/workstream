"""MODEL-USAGE composition root for shared durable ledger implementations."""


def model_profile_reader(session):
    from app.modules.model_usage.profiles import ModelProfileReader

    return ModelProfileReader(session)


def model_call_service(session, *, authority, current_execution, evidence):
    from app.modules.model_usage.service import ModelCallService

    return ModelCallService(
        session,
        authority=authority,
        current_execution=current_execution,
        evidence=evidence,
    )


def model_invocation_grants(session, *, authority, current_execution):
    from app.modules.model_usage.grants import ModelInvocationGrants

    return ModelInvocationGrants(
        session,
        authority=authority,
        current=current_execution,
    )


def model_evidence_custody(session):
    from app.modules.model_usage.owner_ports import ModelEvidenceCustody

    return ModelEvidenceCustody(session)


def model_recovery_sources(session):
    from app.modules.model_usage.owner_ports import ModelRecoverySources

    return ModelRecoverySources(session)


def setup_model_usage_service(session, *, authority, evidence, owner):
    from app.modules.model_usage.setup import SetupModelUsageService

    return SetupModelUsageService(
        session,
        authority=authority,
        evidence=evidence,
        owner=owner,
    )


def setup_model_output_reservations(session, *, owner):
    """Compose MODEL-USAGE-owned setup ART reservations behind its public port."""
    from app.modules.model_usage.output_custody import SetupModelOutputReservations

    return SetupModelOutputReservations(session, owner=owner)


__all__ = (
    "model_call_service",
    "model_evidence_custody",
    "model_invocation_grants",
    "model_profile_reader",
    "model_recovery_sources",
    "setup_model_usage_service",
    "setup_model_output_reservations",
)
