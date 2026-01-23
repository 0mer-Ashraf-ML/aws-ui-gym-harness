"""
Action Timeline Storage

Handles dual storage of action timeline:
- File storage for logs and debugging
- Database storage for fast API queries
"""

import json
import logging
from pathlib import Path
from typing import List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.iteration import Iteration
from app.schemas.action_timeline import TimelineEntry
from app.services.action_timeline_parser import timeline_parser

logger = logging.getLogger(__name__)


class ActionTimelineStorage:
    """Storage service for action timelines"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def save_timeline_to_file(self, iteration_path: Path, entries: List[TimelineEntry]) -> bool:
        """
        Save timeline to file for logging and debugging
        
        Args:
            iteration_path: Path to iteration directory
            entries: List of timeline entries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            timeline_file = iteration_path / "action_timeline.json"
            timeline_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Convert entries to dict for serialization
            entries_dict = [entry.dict() for entry in entries]
            
            # Write pretty-printed JSON for readability
            with open(timeline_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'total_entries': len(entries),
                    'total_actions': sum(1 for e in entries if e.entry_type == 'action'),
                    'entries': entries_dict
                }, f, indent=2, default=str)
            
            self.logger.info(f"✅ Saved timeline to file: {timeline_file} ({len(entries)} entries)")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save timeline to file: {e}")
            return False
    
    async def save_timeline_to_db(self, db: AsyncSession, iteration_id: str, entries: List[TimelineEntry]) -> bool:
        """
        Save timeline to database for fast API queries
        
        Args:
            db: Database session
            iteration_id: Iteration UUID
            entries: List of timeline entries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize timeline to compact JSON
            timeline_json = timeline_parser.serialize_timeline(entries)
            
            # Update iteration with timeline
            result = await db.execute(
                "UPDATE iterations SET action_timeline_json = :timeline_json WHERE uuid = :iteration_id",
                {"timeline_json": timeline_json, "iteration_id": iteration_id}
            )
            await db.commit()
            
            self.logger.info(f"✅ Saved timeline to database for iteration {iteration_id} ({len(entries)} entries)")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ Failed to save timeline to database: {e}")
            await db.rollback()
            return False
    
    async def persist_timeline(
        self, 
        db: AsyncSession, 
        iteration_id: str, 
        iteration_path: Path, 
        entries: List[TimelineEntry]
    ) -> bool:
        """
        Persist timeline to both file and database atomically
        
        Args:
            db: Database session
            iteration_id: Iteration UUID
            iteration_path: Path to iteration directory
            entries: List of timeline entries
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Save to file first (less critical)
            file_success = await self.save_timeline_to_file(iteration_path, entries)
            
            # Save to database (more critical for UI)
            db_success = await self.save_timeline_to_db(db, iteration_id, entries)
            
            if file_success and db_success:
                self.logger.info(f"✅ Successfully persisted timeline for iteration {iteration_id}")
                return True
            elif db_success:
                self.logger.warning(f"⚠️ Saved to database but file save failed for iteration {iteration_id}")
                return True
            else:
                self.logger.error(f"❌ Failed to persist timeline for iteration {iteration_id}")
                return False
                
        except Exception as e:
            self.logger.error(f"❌ Error persisting timeline: {e}")
            return False
    
    async def load_timeline_from_db(self, db: AsyncSession, iteration_id: str) -> List[TimelineEntry]:
        """
        Load timeline from database
        
        Args:
            db: Database session
            iteration_id: Iteration UUID
            
        Returns:
            List of timeline entries
        """
        try:
            result = await db.execute(
                "SELECT action_timeline_json FROM iterations WHERE uuid = :iteration_id",
                {"iteration_id": iteration_id}
            )
            row = result.fetchone()
            
            if row and row[0]:
                return timeline_parser.deserialize_timeline(row[0])
            
            return []
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load timeline from database: {e}")
            return []
    
    def load_timeline_from_file(self, iteration_path: Path) -> List[TimelineEntry]:
        """
        Load timeline from file
        
        Args:
            iteration_path: Path to iteration directory
            
        Returns:
            List of timeline entries
        """
        try:
            timeline_file = iteration_path / "action_timeline.json"
            
            if not timeline_file.exists():
                self.logger.warning(f"Timeline file not found: {timeline_file}")
                return []
            
            with open(timeline_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            entries_data = data.get('entries', [])
            
            # Deserialize entries
            entries = []
            for entry_dict in entries_data:
                entry_type = entry_dict.get('entry_type')
                
                if entry_type == 'model_thinking':
                    from app.schemas.action_timeline import ModelThinkingEntry
                    entries.append(ModelThinkingEntry(**entry_dict))
                elif entry_type == 'model_response':
                    from app.schemas.action_timeline import ModelResponseEntry
                    entries.append(ModelResponseEntry(**entry_dict))
                elif entry_type == 'action':
                    from app.schemas.action_timeline import ActionEntry
                    entries.append(ActionEntry(**entry_dict))
            
            self.logger.info(f"✅ Loaded {len(entries)} timeline entries from file")
            return entries
            
        except Exception as e:
            self.logger.error(f"❌ Failed to load timeline from file: {e}")
            return []


# Singleton instance
timeline_storage = ActionTimelineStorage()

