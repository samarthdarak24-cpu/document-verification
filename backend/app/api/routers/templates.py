"""Template CRUD endpoints (``/api/templates``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import bad_request, get_db, not_found
from app.models import DocumentTemplate, TemplateField
from app.schemas import TemplateCreate, TemplateOut, TemplateUpdate

router = APIRouter(prefix="/templates", tags=["templates"])


def _load(db: Session, template_id: str) -> DocumentTemplate:
    template = db.execute(
        select(DocumentTemplate)
        .options(selectinload(DocumentTemplate.fields))
        .where(DocumentTemplate.id == template_id)
    ).unique().scalar_one_or_none()
    if template is None:
        raise not_found("Template", template_id)
    return template


@router.get("")
def list_templates(
    db: Session = Depends(get_db),
    category: str | None = None,
):
    """All verification templates (optionally filtered by category)."""
    stmt = (
        select(DocumentTemplate)
        .options(selectinload(DocumentTemplate.fields))
        .order_by(DocumentTemplate.name.asc())
    )
    if category:
        stmt = stmt.where(DocumentTemplate.category == category)
    templates = db.execute(stmt).unique().scalars().all()
    return {"items": [TemplateOut.model_validate(t) for t in templates]}


@router.get("/{template_id}")
def get_template(template_id: str, db: Session = Depends(get_db)):
    """One template with its expected fields."""
    return TemplateOut.model_validate(_load(db, template_id))


def _apply_fields(template: DocumentTemplate, fields) -> None:
    """Replace a template's field rows (delete-then-insert keeps positions clean)."""
    template.fields = [
        TemplateField(
            name=field.name,
            data_type=field.data_type,
            required=field.required,
            validation_pattern=field.validation_pattern,
            critical=field.critical,
            position=field.position if field.position else index,
        )
        for index, field in enumerate(fields)
    ]


@router.post("", status_code=201)
def create_template(payload: TemplateCreate, db: Session = Depends(get_db)):
    """Create a verification template."""
    existing = db.execute(
        select(DocumentTemplate).where(DocumentTemplate.name == payload.name)
    ).scalar_one_or_none()
    if existing is not None:
        raise bad_request(f"A template named '{payload.name}' already exists.")

    template = DocumentTemplate(
        name=payload.name,
        category=payload.category,
        description=payload.description,
        required_fields=payload.required_fields,
        optional_fields=payload.optional_fields,
        critical_fields=payload.critical_fields,
        expected_sections=payload.expected_sections,
        section_order=payload.section_order,
        aliases=payload.aliases,
    )
    _apply_fields(template, payload.fields)
    db.add(template)
    db.flush()
    return TemplateOut.model_validate(_load(db, template.id))


@router.put("/{template_id}")
def update_template(
    template_id: str, payload: TemplateUpdate, db: Session = Depends(get_db)
):
    """Partially update a template (only the supplied fields change)."""
    template = _load(db, template_id)
    mapping = {
        "category": "category",
        "description": "description",
        "required_fields": "required_fields",
        "optional_fields": "optional_fields",
        "critical_fields": "critical_fields",
        "expected_sections": "expected_sections",
        "section_order": "section_order",
        "aliases": "aliases",
    }
    data = payload.model_dump(exclude_unset=True)
    for key, attribute in mapping.items():
        if key in data:
            setattr(template, attribute, data[key])
    if "fields" in data and data["fields"] is not None:
        from app.schemas import TemplateFieldIn

        _apply_fields(
            template, [TemplateFieldIn(**field) for field in data["fields"]]
        )
    from datetime import datetime

    template.updated_at = datetime.utcnow()
    db.flush()
    return TemplateOut.model_validate(_load(db, template_id))


@router.delete("/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    """Delete a template (verification runs keep a null template_id)."""
    template = _load(db, template_id)
    if template.category == "custom" and template.name.lower() == "custom":
        raise bad_request("The default 'Custom' template cannot be deleted.")
    name = template.name
    db.delete(template)
    db.flush()
    return {"deleted": template_id, "name": name}
