#!/usr/bin/env python3
"""
Ensure that script-based tasks have a verifier_path.

Usage:
    python backend/scripts/set_verifier_paths.py \
        --path /app/verifiers/DeskZen-Task-01_verifier_v01.py
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Optional

from sqlalchemy import select, update

from app.core.database import AsyncSessionLocal
from app.models.gym import Gym, VerificationStrategy
from app.models.task import Task

DEFAULT_VERIFIER_PATH = "/app/verifiers/DeskZen-Task-01_verifier_v01.py"


async def set_missing_paths(verifier_path: str) -> int:
    async with AsyncSessionLocal() as session:
        stmt = (
            select(Task.uuid)
            .join(Gym, Task.gym)
            .where(
                Gym.verification_strategy == VerificationStrategy.VERIFIER_API_SCRIPT,
                Task.verifier_path.is_(None),
            )
        )
        result = await session.execute(stmt)
        task_ids = [row[0] for row in result.all()]

        if not task_ids:
            return 0

        update_stmt = (
            update(Task)
            .where(Task.uuid.in_(task_ids))
            .values(verifier_path=verifier_path)
        )
        await session.execute(update_stmt)
        await session.commit()
        return len(task_ids)


async def main(verifier_path: str) -> int:
    updated = await set_missing_paths(verifier_path)
    if updated:
        print(f"✅ Updated verifier_path for {updated} task(s).")
    else:
        print("ℹ️  No tasks needed updates.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set verifier_path for script-based tasks.")
    parser.add_argument(
        "--path",
        default=DEFAULT_VERIFIER_PATH,
        help=f"Absolute path to the verifier script (default: {DEFAULT_VERIFIER_PATH})",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.path))

