"""Extended template render tests — binding/secret_ref resolution, project scope."""

from __future__ import annotations

from app.services.template_render import render_template


def test_binding_not_found_returns_error(db_session):
    """Unresolved binding produces error placeholder and warning."""
    result = render_template(db_session, "[[binding.nonexistent]]", project_id=None)
    assert "[ERROR:binding.nonexistent not found]" in result.rendered
    assert result.stats["unresolved_binding"] == 1
    assert any(w["code"] == "NOT_FOUND" and w["kind"] == "binding" for w in result.warnings)


def test_unknown_type_prefix_is_malformed(db_session):
    """Placeholder with type_part not in allowed prefixes is malformed."""
    result = render_template(db_session, "[[unknown.key.here]]", project_id=None)
    assert "[[unknown.key.here]]" in result.rendered
    assert result.stats["malformed"] == 1


def test_secret_ref_renders_tag(db_session):
    """[[secret_ref.xxx]] renders as [secret_ref:xxx]."""
    result = render_template(db_session, "[[secret_ref.my.key]]", project_id=None)
    assert result.rendered == "[secret_ref:my.key]"
    assert result.stats["secret_ref_rendered"] == 1


def test_binding_with_project_scope(client, db_session):
    """Binding resolution with project_id scope returns error when not found in scope."""
    result = render_template(db_session, "[[binding.scoped.svc]]", project_id="nonexistent-pid")
    assert "[ERROR:binding.scoped.svc not found]" in result.rendered
