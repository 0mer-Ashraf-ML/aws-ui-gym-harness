#!/usr/bin/env python3
"""
Container Management API - Endpoints for managing CUA containers
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, List, Optional
import logging

from app.services.cua_container_manager import cua_container_manager
from app.services.container_cleanup_service import container_cleanup_service


router = APIRouter(prefix="/api/containers", tags=["container-management"])
logger = logging.getLogger(__name__)


class ContainerCreateRequest(BaseModel):
    task_id: str
    run_id: str


class ContainerCleanupRequest(BaseModel):
    task_id: str


class ContainerStatsResponse(BaseModel):
    total_containers: int
    healthy_containers: int
    unhealthy_containers: int
    container_details: List[Dict]


@router.post("/create")
async def create_cua_container(request: ContainerCreateRequest):
    """Create a new CUA container for a specific task"""
    try:
        logger.info(f"🐳 API: Creating CUA container for task: {request.task_id}")
        
        cua_urls = await cua_container_manager.create_cua_container(
            request.task_id, 
            request.run_id
        )
        
        logger.info(f"✅ API: CUA container created for task {request.task_id}")
        
        return {
            "success": True,
            "task_id": request.task_id,
            "run_id": request.run_id,
            "container_urls": cua_urls,
            "message": f"CUA container created successfully for task {request.task_id}"
        }
        
    except Exception as e:
        logger.error(f"❌ API: Failed to create CUA container for task {request.task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create CUA container: {str(e)}"
        )


@router.post("/cleanup")
async def cleanup_cua_container(request: ContainerCleanupRequest):
    """Clean up a CUA container for a specific task"""
    try:
        logger.info(f"🧹 API: Cleaning up CUA container for task: {request.task_id}")
        
        success = await cua_container_manager.cleanup_container(request.task_id)
        
        if success:
            logger.info(f"✅ API: CUA container cleaned up for task {request.task_id}")
            return {
                "success": True,
                "task_id": request.task_id,
                "message": f"CUA container cleaned up successfully for task {request.task_id}"
            }
        else:
            logger.warning(f"⚠️ API: Failed to clean up CUA container for task {request.task_id}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to clean up CUA container for task {request.task_id}"
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Error cleaning up CUA container for task {request.task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up CUA container: {str(e)}"
        )


@router.post("/cleanup-all")
async def cleanup_all_containers(background_tasks: BackgroundTasks):
    """Clean up all active CUA containers"""
    try:
        logger.info("🧹 API: Cleaning up all CUA containers")
        
        # Run cleanup in background
        background_tasks.add_task(cua_container_manager.cleanup_all_containers)
        
        return {
            "success": True,
            "message": "Cleanup of all containers initiated in background"
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error initiating cleanup of all containers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error initiating cleanup: {str(e)}"
        )


@router.get("/stats")
async def get_container_stats():
    """Get statistics about active CUA containers"""
    try:
        health_status = await cua_container_manager.health_check()
        
        return {
            "success": True,
            "stats": {
                "total_containers": health_status['total_containers'],
                "healthy_containers": health_status['healthy_containers'],
                "unhealthy_containers": health_status['unhealthy_containers'],
                "container_details": health_status['container_details']
            },
            "cleanup_service": container_cleanup_service.get_cleanup_stats()
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error getting container stats: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting container stats: {str(e)}"
        )


@router.get("/list")
async def list_active_containers():
    """List all active CUA containers"""
    try:
        containers = cua_container_manager.list_active_containers()
        
        return {
            "success": True,
            "containers": containers,
            "count": len(containers)
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error listing containers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing containers: {str(e)}"
        )


@router.get("/info/{task_id}")
async def get_container_info(task_id: str):
    """Get information about a specific container"""
    try:
        container_info = cua_container_manager.get_container_info(task_id)
        
        if not container_info:
            raise HTTPException(
                status_code=404,
                detail=f"No container found for task {task_id}"
            )
        
        return {
            "success": True,
            "task_id": task_id,
            "container_info": container_info
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ API: Error getting container info for task {task_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting container info: {str(e)}"
        )


@router.post("/cleanup-service/start")
async def start_cleanup_service():
    """Start the background cleanup service"""
    try:
        await container_cleanup_service.start_cleanup_service()
        
        return {
            "success": True,
            "message": "Cleanup service started successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error starting cleanup service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error starting cleanup service: {str(e)}"
        )


@router.post("/cleanup-service/stop")
async def stop_cleanup_service():
    """Stop the background cleanup service"""
    try:
        await container_cleanup_service.stop_cleanup_service()
        
        return {
            "success": True,
            "message": "Cleanup service stopped successfully"
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error stopping cleanup service: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error stopping cleanup service: {str(e)}"
        )


@router.post("/cleanup-orphaned")
async def cleanup_orphaned_containers():
    """Clean up orphaned containers that are not tracked"""
    try:
        logger.info("🧹 API: Cleaning up orphaned containers")
        
        orphaned_count = await container_cleanup_service.cleanup_orphaned_containers()
        
        return {
            "success": True,
            "orphaned_containers_cleaned": orphaned_count,
            "message": f"Cleaned up {orphaned_count} orphaned containers"
        }
        
    except Exception as e:
        logger.error(f"❌ API: Error cleaning up orphaned containers: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error cleaning up orphaned containers: {str(e)}"
        )
