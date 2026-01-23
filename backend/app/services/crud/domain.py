"""
Domain CRUD operations
"""

from typing import List, Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain import Domain
from app.schemas.domain import DomainCreate, DomainUpdate


class DomainCRUD:
    """Domain CRUD operations"""
    
    async def get_by_id(self, db: AsyncSession, domain_id: str) -> Optional[Domain]:
        """Get domain by UUID"""
        result = await db.execute(select(Domain).where(Domain.uuid == domain_id))
        return result.scalar_one_or_none()
    
    async def get_by_domain(self, db: AsyncSession, domain: str) -> Optional[Domain]:
        """Get domain by domain name"""
        result = await db.execute(select(Domain).where(Domain.domain == domain.lower()))
        return result.scalar_one_or_none()
    
    async def create(self, db: AsyncSession, domain_data: DomainCreate) -> Domain:
        """Create new domain"""
        db_domain = Domain(
            domain=domain_data.domain.lower(),
            is_active=domain_data.is_active
        )
        
        db.add(db_domain)
        await db.commit()
        await db.refresh(db_domain)
        return db_domain
    
    async def update(self, db: AsyncSession, domain_id: str, domain_data: DomainUpdate) -> Optional[Domain]:
        """Update domain"""
        await db.execute(
            update(Domain)
            .where(Domain.uuid == domain_id)
            .values(**domain_data.dict(exclude_unset=True))
        )
        await db.commit()
        return await self.get_by_id(db, domain_id)
    
    async def delete(self, db: AsyncSession, domain_id: str) -> bool:
        """Delete domain"""
        result = await db.execute(delete(Domain).where(Domain.uuid == domain_id))
        await db.commit()
        return result.rowcount > 0
    
    async def get_all(self, db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Domain]:
        """Get all domains"""
        result = await db.execute(
            select(Domain)
            .offset(skip)
            .limit(limit)
            .order_by(Domain.created_at.desc())
        )
        return result.scalars().all()
    
    async def get_active_domains(self, db: AsyncSession) -> List[Domain]:
        """Get all active domains"""
        result = await db.execute(
            select(Domain)
            .where(Domain.is_active == True)
            .order_by(Domain.domain)
        )
        return result.scalars().all()
    
    async def is_domain_whitelisted(self, db: AsyncSession, email: str) -> bool:
        """Check if email domain is whitelisted"""
        if '@' not in email:
            return False
        
        domain = email.split('@')[1].lower()
        result = await db.execute(
            select(Domain)
            .where(Domain.domain == domain, Domain.is_active == True)
        )
        return result.scalar_one_or_none() is not None
    
    async def whitelist_domain(self, db: AsyncSession, domain: str) -> Optional[Domain]:
        """Whitelist a domain. Creates domain if doesn't exist."""
        existing_domain = await self.get_by_domain(db, domain)
        
        if not existing_domain:
            # Create a new domain record
            domain_data = DomainCreate(domain=domain, is_active=True)
            return await self.create(db, domain_data)
        else:
            # Update existing domain to be active
            await db.execute(
                update(Domain)
                .where(Domain.domain == domain.lower())
                .values(is_active=True)
            )
            await db.commit()
            return await self.get_by_domain(db, domain)
    
    async def remove_from_whitelist(self, db: AsyncSession, domain: str) -> Optional[Domain]:
        """Remove domain from whitelist (deactivate)"""
        domain_obj = await self.get_by_domain(db, domain)
        if not domain_obj:
            return None
        
        await db.execute(
            update(Domain)
            .where(Domain.domain == domain.lower())
            .values(is_active=False)
        )
        await db.commit()
        return await self.get_by_domain(db, domain)


# Create instance
domain_crud = DomainCRUD()
