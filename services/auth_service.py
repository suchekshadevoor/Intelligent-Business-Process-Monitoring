"""
Authentication and Role-Based Access Control (RBAC) Service.
Provides cryptographic password hashing, user verification, user management, and permission matrix checks.
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from database.schema import User, AuditLog, utc_now
from config.settings import logger, settings

# Role hierarchy and permissions mapping
PERMISSIONS = {
    "admin": ["manage_users", "manage_rules", "resolve_alerts", "assign_alerts", "run_monitoring", "create_records", "import_data", "view_reports", "view_dashboard"],
    "manager": ["manage_rules", "resolve_alerts", "assign_alerts", "run_monitoring", "create_records", "import_data", "view_reports", "view_dashboard"],
    "analyst": ["view_reports", "view_dashboard", "import_data"],
}


class AuthService:
    PASSWORD_HASH_ITERATIONS = 600_000

    @staticmethod
    def issue_access_token(user_id: int) -> tuple[str, int]:
        """Create a signed, expiring bearer token for an authenticated user."""
        expires_at = int(time.time()) + settings.API_TOKEN_TTL_MINUTES * 60
        payload = json.dumps({"sub": user_id, "exp": expires_at}, separators=(",", ":")).encode("utf-8")
        encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=")
        signature = hmac.new(
            settings.API_TOKEN_SECRET.encode("utf-8"), encoded_payload, hashlib.sha256
        ).digest()
        token = b".".join((encoded_payload, base64.urlsafe_b64encode(signature).rstrip(b"=")))
        return token.decode("ascii"), expires_at

    @staticmethod
    def verify_access_token(token: str) -> Optional[int]:
        """Return the user ID for a valid token, otherwise None."""
        try:
            encoded_payload, encoded_signature = token.encode("ascii").split(b".", maxsplit=1)
            signature = base64.urlsafe_b64decode(encoded_signature + b"=" * (-len(encoded_signature) % 4))
            expected_signature = hmac.new(
                settings.API_TOKEN_SECRET.encode("utf-8"), encoded_payload, hashlib.sha256
            ).digest()
            if not hmac.compare_digest(signature, expected_signature):
                return None

            payload = json.loads(
                base64.urlsafe_b64decode(encoded_payload + b"=" * (-len(encoded_payload) % 4))
            )
            user_id = int(payload["sub"])
            if user_id < 1 or int(payload["exp"]) <= int(time.time()):
                return None
            return user_id
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error, json.JSONDecodeError):
            return None

    @staticmethod
    def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
        """Generate a salted PBKDF2 hash with a self-describing salt value."""
        raw_salt = secrets.token_hex(16) if not salt else salt
        if raw_salt.startswith("pbkdf2_sha256$"):
            _, iterations, raw_salt = raw_salt.split("$", maxsplit=2)
            iteration_count = int(iterations)
        else:
            iteration_count = AuthService.PASSWORD_HASH_ITERATIONS

        hashed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(raw_salt),
            iteration_count,
        ).hex()
        return hashed, f"pbkdf2_sha256${iteration_count}${raw_salt}"

    @classmethod
    def verify_password(cls, password: str, hashed_password: str, salt: str) -> bool:
        """Verify PBKDF2 hashes and legacy salted SHA-256 hashes during migration."""
        if salt.startswith("pbkdf2_sha256$"):
            expected_hash, _ = cls.hash_password(password, salt)
        else:
            expected_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
        return secrets.compare_digest(expected_hash, hashed_password)

    @classmethod
    def authenticate_user(cls, db: Session, username_or_email: str, password: str) -> Optional[User]:
        """Verify user credentials and return User if valid and active."""
        identifier = username_or_email.strip().lower()
        user = db.query(User).filter(
            (User.username.ilike(identifier)) | (User.email.ilike(identifier))
        ).first()

        if not user:
            logger.warning(f"Authentication attempt failed: User '{identifier}' not found.")
            return None

        if not user.is_active:
            logger.warning(f"Authentication attempt failed: User '{identifier}' is deactivated.")
            return None

        if cls.verify_password(password, user.hashed_password, user.salt):
            if not user.salt.startswith("pbkdf2_sha256$"):
                user.hashed_password, user.salt = cls.hash_password(password)
            logger.info(f"User '{user.username}' successfully authenticated (Role: {user.role}).")
            return user
        else:
            logger.warning(f"Authentication attempt failed: Invalid password for '{user.username}'.")
            return None

    @classmethod
    def create_user(
        cls,
        db: Session,
        username: str,
        email: str,
        password: str,
        role: str = "analyst",
        created_by: str = "System",
    ) -> Dict[str, Any]:
        """Create and persist a new user."""
        role_clean = role.lower().strip()
        if role_clean not in PERMISSIONS:
            return {"success": False, "error": f"Invalid role '{role}'. Allowed roles: {list(PERMISSIONS.keys())}"}

        # Check unique constraints
        if db.query(User).filter(User.username.ilike(username.strip())).first():
            return {"success": False, "error": f"Username '{username}' already exists."}
        if db.query(User).filter(User.email.ilike(email.strip())).first():
            return {"success": False, "error": f"Email '{email}' already registered."}

        hashed, salt = cls.hash_password(password)
        new_user = User(
            username=username.strip(),
            email=email.strip().lower(),
            hashed_password=hashed,
            salt=salt,
            role=role_clean,
            is_active=True,
            created_at=utc_now(),
        )
        db.add(new_user)
        db.flush()

        # Audit log entry
        db.add(
            AuditLog(
                entity_type="user",
                entity_id=str(new_user.id),
                action="CREATE_USER",
                user_or_system=created_by,
                details_json=f'{{"username": "{new_user.username}", "role": "{new_user.role}"}}',
                timestamp=utc_now(),
            )
        )
        db.commit()
        return {"success": True, "user": new_user.to_dict()}

    @staticmethod
    def list_users(db: Session) -> List[Dict[str, Any]]:
        """Return safe representations of all registered users."""
        users = db.query(User).order_by(User.id.asc()).all()
        return [u.to_dict() for u in users]

    @staticmethod
    def update_user_role(db: Session, user_id: int, new_role: str, updated_by: str = "Admin") -> Dict[str, Any]:
        """Update role for an existing user."""
        new_role = new_role.lower().strip()
        if new_role not in PERMISSIONS:
            return {"success": False, "error": f"Invalid role: {new_role}"}

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "User not found."}

        old_role = user.role
        user.role = new_role
        db.add(
            AuditLog(
                entity_type="user",
                entity_id=str(user.id),
                action="UPDATE_ROLE",
                user_or_system=updated_by,
                details_json=f'{{"from": "{old_role}", "to": "{new_role}"}}',
                timestamp=utc_now(),
            )
        )
        db.commit()
        return {"success": True, "user": user.to_dict()}

    @staticmethod
    def toggle_user_active(db: Session, user_id: int, updated_by: str = "Admin") -> Dict[str, Any]:
        """Toggle active/deactivated status of a user."""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"success": False, "error": "User not found."}

        user.is_active = not user.is_active
        action = "ACTIVATE_USER" if user.is_active else "DEACTIVATE_USER"
        db.add(
            AuditLog(
                entity_type="user",
                entity_id=str(user.id),
                action=action,
                user_or_system=updated_by,
                details_json=f'{{"is_active": {user.is_active}}}',
                timestamp=utc_now(),
            )
        )
        db.commit()
        return {"success": True, "user": user.to_dict()}

    @staticmethod
    def is_authorized(role: Optional[str], permission: str) -> bool:
        """Check if role grants requested permission."""
        if not role:
            return False
        return permission in PERMISSIONS.get(role.lower(), [])
