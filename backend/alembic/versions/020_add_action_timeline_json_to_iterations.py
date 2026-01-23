"""add action_timeline_json to iterations

Revision ID: 020
Revises: 019
Create Date: 2025-11-14 16:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import UUID
from pathlib import Path
import json
import logging

# revision identifiers, used by Alembic.
revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None

logger = logging.getLogger('alembic.migration')


def upgrade():
    # Step 1: Add action_timeline_json column if it doesn't already exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'iterations' AND column_name = 'action_timeline_json'
            ) THEN
                ALTER TABLE iterations ADD COLUMN action_timeline_json TEXT;
            END IF;
        END $$;
    """)
    
    # Step 2: Back-populate existing iterations with timeline data
    bind = op.get_bind()
    session = Session(bind=bind)
    
    try:
        # Import services after column is added
        from app.services.action_timeline_parser import timeline_parser
        from app.core.config import settings
        
        # Query all iterations with their execution info
        result = session.execute(sa.text("""
            SELECT 
                i.uuid as iteration_id,
                i.iteration_number,
                e.uuid as execution_id,
                e.execution_folder_name,
                e.task_identifier
            FROM iterations i
            JOIN executions e ON i.execution_id = e.uuid
            WHERE i.action_timeline_json IS NULL
        """))
        
        iterations = result.fetchall()
        logger.info(f"📊 Found {len(iterations)} iterations to back-populate")
        
        results_dir = Path(settings.RESULTS_DIR)
        populated_count = 0
        skipped_count = 0
        
        for iteration in iterations:
            try:
                # Build path to conversation history
                iteration_path = (
                    results_dir / 
                    iteration.execution_folder_name / 
                    iteration.task_identifier / 
                    f"iteration_{iteration.iteration_number}"
                )
                
                conversation_dir = iteration_path / "conversation_history"
                
                if not conversation_dir.exists():
                    skipped_count += 1
                    continue
                
                # Find conversation history file
                conversation_files = list(conversation_dir.glob("*_task_execution_conversation.json"))
                
                if not conversation_files:
                    skipped_count += 1
                    continue
                
                conversation_file = conversation_files[0]
                
                # Parse the conversation history
                timeline_entries = timeline_parser.parse_conversation_history(conversation_file)
                
                if timeline_entries:
                    # Serialize to JSON
                    timeline_json = timeline_parser.serialize_timeline(timeline_entries)
                    
                    # Update the iteration
                    session.execute(
                        sa.text("""
                            UPDATE iterations 
                            SET action_timeline_json = :timeline_json 
                            WHERE uuid = :iteration_id
                        """),
                        {
                            "timeline_json": timeline_json,
                            "iteration_id": str(iteration.iteration_id)
                        }
                    )
                    populated_count += 1
                    
                    if populated_count % 10 == 0:
                        logger.info(f"✅ Populated {populated_count} iterations...")
                        
            except Exception as e:
                logger.warning(f"⚠️ Failed to populate iteration {iteration.iteration_id}: {e}")
                skipped_count += 1
                continue
        
        session.commit()
        logger.info(f"✅ Migration complete: {populated_count} populated, {skipped_count} skipped")
        
    except Exception as e:
        logger.error(f"❌ Error during data migration: {e}")
        session.rollback()
        # Don't fail the migration if back-population fails
        logger.warning("⚠️ Column added but data back-population failed. Data can be populated later.")
    finally:
        session.close()


def downgrade():
    # Remove action_timeline_json column from iterations table
    op.drop_column('iterations', 'action_timeline_json')

