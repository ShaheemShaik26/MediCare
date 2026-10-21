from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models.user import LifestyleProfile, User
from app.schemas.lifestyle import LifestyleProfileSchema, LifestyleProfileUpdate

router = APIRouter(prefix="/api/lifestyle", tags=["lifestyle"])


@router.get("", response_model=LifestyleProfileSchema | None)
def get_lifestyle_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return db.query(LifestyleProfile).filter(LifestyleProfile.owner_id == current_user.id).first()


@router.put("", response_model=LifestyleProfileSchema)
def update_lifestyle_profile(
    payload: LifestyleProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(LifestyleProfile).filter(LifestyleProfile.owner_id == current_user.id).first()
    if profile is None:
        profile = LifestyleProfile(owner_id=current_user.id)
        db.add(profile)

    for field, value in payload.model_dump().items():
        setattr(profile, field, value.strip() or None if isinstance(value, str) else value)

    db.commit()
    db.refresh(profile)
    return profile
