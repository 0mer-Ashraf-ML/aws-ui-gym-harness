"""
Utility functions for testing
"""
from faker import Faker
from typing import Dict, Any
from datetime import datetime

fake = Faker()


def create_mock_user_data(**kwargs) -> Dict[str, Any]:
    """Create mock user data for testing."""
    return {
        "id": fake.uuid4(),
        "email": fake.email(),
        "name": fake.name(),
        "is_active": True,
        "is_admin": False,
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }


def create_mock_gym_data(**kwargs) -> Dict[str, Any]:
    """Create mock gym data for testing."""
    return {
        "id": fake.uuid4(),
        "name": fake.catch_phrase(),
        "description": fake.text(),
        "verification_strategy": "manual",
        "is_active": True,
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }


def create_mock_task_data(**kwargs) -> Dict[str, Any]:
    """Create mock task data for testing."""
    return {
        "id": fake.uuid4(),
        "gym_id": fake.uuid4(),
        "name": fake.catch_phrase(),
        "prompt": fake.text(),
        "model_type": "openai",
        "model_name": "gpt-4",
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }


def create_mock_execution_data(**kwargs) -> Dict[str, Any]:
    """Create mock execution data for testing."""
    return {
        "id": fake.uuid4(),
        "status": "pending",
        "started_at": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }


def create_mock_iteration_data(**kwargs) -> Dict[str, Any]:
    """Create mock iteration data for testing."""
    return {
        "id": fake.uuid4(),
        "execution_id": fake.uuid4(),
        "status": "pending",
        "iteration_number": fake.random_int(min=1, max=10),
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }


def create_mock_batch_data(**kwargs) -> Dict[str, Any]:
    """Create mock batch data for testing."""
    return {
        "id": fake.uuid4(),
        "name": fake.catch_phrase(),
        "description": fake.text(),
        "status": "pending",
        "task_count": fake.random_int(min=1, max=100),
        "created_at": datetime.utcnow().isoformat(),
        **kwargs
    }

