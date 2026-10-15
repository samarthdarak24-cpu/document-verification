"""Settings endpoints (``/api/settings``)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import bad_request, get_db, not_found
from app.models import DEFAULT_SETTINGS, ApplicationSetting, load_settings, seed_settings
from app.schemas import SettingOut, SettingsResponse

router = APIRouter(prefix="/settings", tags=["settings"])

DEFAULTS = {key: value for key, value in DEFAULT_SETTINGS}

#: Settings the API is allowed to update (anything else is rejected).
EDITABLE = set(DEFAULTS)


@router.get("")
def get_settings_endpoint(db: Session = Depends(get_db)):
    """Current settings merged over the documented defaults."""
    return SettingsResponse(settings=load_settings(db), defaults=dict(DEFAULTS))


@router.put("/{key}")
def update_setting(key: str, payload: dict, db: Session = Depends(get_db)):
    """Update one setting; unknown keys are rejected rather than silently stored."""
    if key not in EDITABLE:
        raise bad_request(
            f"Unknown setting '{key}'. Editable keys: {', '.join(sorted(EDITABLE))}."
        )
    value = payload.get("value")
    row = db.execute(
        select(ApplicationSetting).where(ApplicationSetting.key == key)
    ).scalar_one_or_none()
    if row is None:
        row = ApplicationSetting(key=key, value_json=value)
        db.add(row)
    else:
        row.value_json = value
    db.flush()
    return SettingOut.model_validate(row)


@router.post("/reset", status_code=200)
def reset_settings(db: Session = Depends(get_db)):
    """Restore every setting to its documented default."""
    rows = db.execute(select(ApplicationSetting)).scalars().all()
    for row in rows:
        if row.key in DEFAULTS:
            row.value_json = DEFAULTS[row.key]
    seed_settings(db)
    db.flush()
    return {"settings": load_settings(db), "reset": len(rows)}
