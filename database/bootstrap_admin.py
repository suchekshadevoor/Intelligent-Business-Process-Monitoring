"""Create the first administrator without enabling demo data."""

from getpass import getpass

from database.connection import get_db, init_db
from database.schema import User
from services.auth_service import AuthService


def main() -> None:
    init_db()
    with get_db() as db:
        if db.query(User.id).filter(User.role == "admin", User.is_active.is_(True)).first():
            print("An active administrator already exists.")
            return

        username = input("Administrator username: ").strip()
        email = input("Administrator email: ").strip()
        password = getpass("Password (minimum 12 characters): ")
        confirmation = getpass("Confirm password: ")

        if not username or not email:
            raise SystemExit("Username and email are required.")
        if len(password) < 12:
            raise SystemExit("Password must be at least 12 characters.")
        if password != confirmation:
            raise SystemExit("Passwords did not match.")

        result = AuthService.create_user(db, username, email, password, role="admin")
        if not result["success"]:
            raise SystemExit(result["error"])
        print(f"Administrator '{username}' created.")


if __name__ == "__main__":
    main()