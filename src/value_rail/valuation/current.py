"""Read current access proofs without rewriting historical evaluation inputs."""
from ..storage.orm import OperatorProfileRow


def with_current_prerequisites(s, evaluation, inputs, settings):
    if inputs.is_synthetic:
        return inputs
    operator = s.get(OperatorProfileRow, evaluation.operator_profile_id) if evaluation.operator_profile_id else None
    configured = settings.file_config.operator
    if configured is None or operator is None or operator.name != configured.name:
        operator = None
    caps = operator.capabilities if operator and not operator.is_synthetic else {}
    proofs = caps.get("_evidence", {})
    prerequisites = []
    for p in inputs.prerequisites:
        status = caps.get(p.name, "unknown")
        if status not in ("proven", "unproven", "unknown"):
            status = "unknown"
        prerequisites.append(p.model_copy(update={"status": status, "evidence_ref": proofs.get(p.name, "unknown")}))
    return inputs.model_copy(update={"prerequisites": prerequisites})
