"""Current selected request identity mutations for authority and lineage controls."""

from app.modules.checkers.api.selected_post_submit import make_selected_post_submit_request


def change_request(source, **changes):
    fields = source.model_dump(exclude={"request_sha256"})
    fields.update(changes)
    return make_selected_post_submit_request(**fields)
