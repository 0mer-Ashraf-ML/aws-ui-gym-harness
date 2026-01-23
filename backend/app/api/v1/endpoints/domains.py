"""
Domain management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_admin_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.domain import (DomainCreate, DomainListResponse, DomainResponse,
                                DomainUpdate, WhitelistDomainRequest)
from app.services.crud.domain import domain_crud

router = APIRouter()


@router.get("/", response_model=DomainListResponse)
async def get_all_domains(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get all domains (admin only)
    """
    domains = await domain_crud.get_all(db, skip=skip, limit=limit)
    return DomainListResponse(domains=domains, total=len(domains))


@router.get("/active", response_model=list[DomainResponse])
async def get_active_domains(
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get all active domains (admin only)
    """
    domains = await domain_crud.get_active_domains(db)
    return domains


@router.get("/{domain_id}", response_model=DomainResponse)
async def get_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Get domain by ID (admin only)
    """
    domain = await domain_crud.get_by_id(db, domain_id)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    return domain


@router.post("/", response_model=DomainResponse)
async def create_domain(
    domain_data: DomainCreate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Create a new domain (admin only)
    """
    # Check if domain already exists
    existing_domain = await domain_crud.get_by_domain(db, domain_data.domain)
    if existing_domain:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Domain already exists"
        )
    
    domain = await domain_crud.create(db, domain_data)
    return domain


@router.post("/whitelist", response_model=DomainResponse)
async def whitelist_domain(
    whitelist_request: WhitelistDomainRequest,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Whitelist a domain (admin only)
    """
    domain = await domain_crud.whitelist_domain(db, whitelist_request.domain)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to whitelist domain"
        )
    return domain


@router.put("/{domain_id}", response_model=DomainResponse)
async def update_domain(
    domain_id: str,
    domain_data: DomainUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Update domain (admin only)
    """
    domain = await domain_crud.update(db, domain_id, domain_data)
    if not domain:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    return domain


@router.delete("/{domain_id}")
async def delete_domain(
    domain_id: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Delete domain (admin only)
    """
    success = await domain_crud.delete(db, domain_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    return {"message": "Domain deleted successfully"}


@router.delete("/domain/{domain}")
async def remove_domain_from_whitelist(
    domain: str,
    db: AsyncSession = Depends(get_db),
    current_admin: User = Depends(get_current_admin_user)
):
    """
    Remove domain from whitelist (deactivate) (admin only)
    """
    domain_obj = await domain_crud.remove_from_whitelist(db, domain)
    if not domain_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Domain not found"
        )
    return {"message": f"Domain {domain} removed from whitelist"}
