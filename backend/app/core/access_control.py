"""
Access control for admin/user roles using ADMIN_EMAILS from .env (harness_main backend).

Admins are determined by ADMIN_EMAILS environment variable (comma-separated list).
All other users are treated as regular users and can log in.
"""

from typing import Literal, Optional

from app.core.config import settings

Role = Literal["admin", "user"]


class AccessControl:
    """Utility class for access control based on ADMIN_EMAILS from .env."""

    @classmethod
    def _get_admin_emails(cls) -> set[str]:
        """Get the set of admin emails from settings."""
        return set(settings.admin_emails_list)

    @classmethod
    def is_enabled(cls) -> bool:
        """Access control is always enabled (no Excel sheet required)."""
        return True

    @classmethod
    def get_role_for_email(cls, email: str) -> Optional[Role]:
        """
        Return the role for the given email based on ADMIN_EMAILS.

        Returns:
            "admin" if email is in ADMIN_EMAILS, "user" otherwise.
        """
        normalized = email.strip().lower()
        admin_emails = cls._get_admin_emails()
        if normalized in admin_emails:
            return "admin"
        return "user"

    @classmethod
    def is_admin_email(cls, email: str) -> bool:
        """Convenience helper to check if email is an admin."""
        return cls.get_role_for_email(email) == "admin"

    @classmethod
    def is_user_email(cls, email: str) -> bool:
        """Convenience helper to check if email is a non-admin user."""
        return cls.get_role_for_email(email) == "user"


