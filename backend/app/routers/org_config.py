from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import get_org_user, org_id, require_permission
from app.core.rbac import ASSIGNABLE_ROLES, P
from app.db.database import get_db
from app.db.models import Category, SlaPolicy, Team, TeamMember, User
from app.schemas.common import MessageOut
from app.schemas.organizations import (
    CategoryIn,
    CategoryOut,
    SlaPoliciesIn,
    SlaPolicyItem,
    TeamIn,
    TeamMembersIn,
    TeamOut,
)
from app.services import audit
from app.services.guards import ensure_not_demo

router = APIRouter(tags=["organization configuration"])


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------
def _team_out(db: Session, team: Team) -> TeamOut:
    member_ids = [uid for (uid,) in db.query(TeamMember.user_id).filter(TeamMember.team_id == team.id)]
    return TeamOut(id=team.id, name=team.name, description=team.description, member_ids=sorted(member_ids))


def _load_team(db: Session, team_id: int, tenant_id: int) -> Team:
    team = db.query(Team).filter(Team.id == team_id, Team.tenant_id == tenant_id).first()
    if team is None:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.get("/teams", response_model=list[TeamOut])
def list_teams(user: User = Depends(require_permission(P.TEAMS_READ)), db: Session = Depends(get_db)):
    teams = db.query(Team).filter(Team.tenant_id == org_id(user)).order_by(Team.name).all()
    return [_team_out(db, t) for t in teams]


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
def create_team(
    payload: TeamIn, user: User = Depends(require_permission(P.TEAMS_MANAGE)), db: Session = Depends(get_db)
):
    team = Team(tenant_id=org_id(user), name=payload.name.strip(), description=payload.description)
    db.add(team)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A team with this name already exists") from None
    audit.record(
        db,
        "team.create",
        tenant_id=org_id(user),
        actor=user,
        entity_type="team",
        entity_id=team.id,
        changes={"name": team.name},
    )
    db.commit()
    return _team_out(db, team)


@router.patch("/teams/{team_id}", response_model=TeamOut)
def update_team(
    team_id: int,
    payload: TeamIn,
    user: User = Depends(require_permission(P.TEAMS_MANAGE)),
    db: Session = Depends(get_db),
):
    team = _load_team(db, team_id, org_id(user))
    changes = audit.diff(
        {"name": team.name, "description": team.description},
        {"name": payload.name.strip(), "description": payload.description},
    )
    team.name, team.description = payload.name.strip(), payload.description
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A team with this name already exists") from None
    if changes:
        audit.record(
            db,
            "team.update",
            tenant_id=org_id(user),
            actor=user,
            entity_type="team",
            entity_id=team.id,
            changes=changes,
        )
    db.commit()
    return _team_out(db, team)


@router.put("/teams/{team_id}/members", response_model=TeamOut)
def set_team_members(
    team_id: int,
    payload: TeamMembersIn,
    user: User = Depends(require_permission(P.TEAMS_MANAGE)),
    db: Session = Depends(get_db),
):
    team = _load_team(db, team_id, org_id(user))
    wanted = set(payload.user_ids)
    if wanted:
        valid = {
            uid
            for (uid,) in db.query(User.id).filter(
                User.id.in_(wanted),
                User.tenant_id == org_id(user),
                User.role.in_(list(ASSIGNABLE_ROLES)),
            )
        }
        if valid != wanted:
            raise HTTPException(status_code=422, detail="Team members must be staff of this organization")
    current = {uid for (uid,) in db.query(TeamMember.user_id).filter(TeamMember.team_id == team.id)}
    for uid in current - wanted:
        db.query(TeamMember).filter(TeamMember.team_id == team.id, TeamMember.user_id == uid).delete()
    for uid in wanted - current:
        db.add(TeamMember(team_id=team.id, user_id=uid))
    if current != wanted:
        audit.record(
            db,
            "team.members",
            tenant_id=org_id(user),
            actor=user,
            entity_type="team",
            entity_id=team.id,
            changes={"added": sorted(wanted - current), "removed": sorted(current - wanted)},
        )
    db.commit()
    return _team_out(db, team)


@router.delete("/teams/{team_id}", response_model=MessageOut)
def delete_team(team_id: int, user: User = Depends(require_permission(P.TEAMS_MANAGE)), db: Session = Depends(get_db)):
    ensure_not_demo(db, user, "Deleting teams")
    team = _load_team(db, team_id, org_id(user))
    audit.record(
        db,
        "team.delete",
        tenant_id=org_id(user),
        actor=user,
        entity_type="team",
        entity_id=team.id,
        changes={"name": team.name},
    )
    db.delete(team)
    db.commit()
    return {"message": "Team deleted"}


# ---------------------------------------------------------------------------
# Categories (taxonomy + routing rules)
# ---------------------------------------------------------------------------
@router.get("/categories", response_model=list[CategoryOut])
def list_categories(include_inactive: bool = False, user: User = Depends(get_org_user), db: Session = Depends(get_db)):
    q = db.query(Category).filter(Category.tenant_id == org_id(user))
    if not include_inactive:
        q = q.filter(Category.is_active.is_(True))
    return q.order_by(Category.id).all()


def _check_team(db: Session, team_id: int | None, tenant_id: int) -> None:
    if team_id is not None:
        _load_team(db, team_id, tenant_id)


@router.post("/categories", response_model=CategoryOut, status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CategoryIn, user: User = Depends(require_permission(P.CATEGORIES_MANAGE)), db: Session = Depends(get_db)
):
    _check_team(db, payload.default_team_id, org_id(user))
    cat = Category(tenant_id=org_id(user), **payload.model_dump())
    db.add(cat)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A category with this name already exists") from None
    audit.record(
        db,
        "category.create",
        tenant_id=org_id(user),
        actor=user,
        entity_type="category",
        entity_id=cat.id,
        changes=payload.model_dump(),
    )
    db.commit()
    return cat


@router.put("/categories/{category_id}", response_model=CategoryOut)
def update_category(
    category_id: int,
    payload: CategoryIn,
    user: User = Depends(require_permission(P.CATEGORIES_MANAGE)),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == category_id, Category.tenant_id == org_id(user)).first()
    if cat is None:
        raise HTTPException(status_code=404, detail="Category not found")
    _check_team(db, payload.default_team_id, org_id(user))
    new = payload.model_dump()
    changes = audit.diff({k: getattr(cat, k) for k in new}, new)
    for k, v in new.items():
        setattr(cat, k, v)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A category with this name already exists") from None
    if changes:
        audit.record(
            db,
            "category.update",
            tenant_id=org_id(user),
            actor=user,
            entity_type="category",
            entity_id=cat.id,
            changes=changes,
        )
    db.commit()
    return cat


# ---------------------------------------------------------------------------
# SLA policies
# ---------------------------------------------------------------------------
@router.get("/sla-policies", response_model=list[SlaPolicyItem])
def get_sla_policies(user: User = Depends(require_permission(P.ORG_READ)), db: Session = Depends(get_db)):
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    rows = db.query(SlaPolicy).filter(SlaPolicy.tenant_id == org_id(user)).all()
    return sorted(rows, key=lambda r: order.get(r.priority, 9))


@router.put("/sla-policies", response_model=list[SlaPolicyItem])
def set_sla_policies(
    payload: SlaPoliciesIn, user: User = Depends(require_permission(P.SLA_MANAGE)), db: Session = Depends(get_db)
):
    ensure_not_demo(db, user, "Changing SLA policies")
    for item in payload.policies:
        if item.first_response_minutes > item.resolution_minutes:
            raise HTTPException(
                status_code=422, detail=f"{item.priority}: first response cannot exceed resolution time"
            )
    existing = {p.priority: p for p in db.query(SlaPolicy).filter(SlaPolicy.tenant_id == org_id(user))}
    changes = {}
    for item in payload.policies:
        row = existing.get(item.priority)
        new = (item.first_response_minutes, item.resolution_minutes)
        if row is None:
            db.add(SlaPolicy(tenant_id=org_id(user), **item.model_dump()))
            changes[item.priority] = [None, list(new)]
        elif (row.first_response_minutes, row.resolution_minutes) != new:
            changes[item.priority] = [[row.first_response_minutes, row.resolution_minutes], list(new)]
            row.first_response_minutes, row.resolution_minutes = new
    if changes:
        # Applies to tickets created from now on; existing due dates are unchanged.
        audit.record(
            db,
            "sla_policy.update",
            tenant_id=org_id(user),
            actor=user,
            entity_type="sla_policy",
            entity_id=org_id(user),
            changes=changes,
        )
    db.commit()
    return get_sla_policies(user, db)
