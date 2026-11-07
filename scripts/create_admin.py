import argparse
import getpass
import secrets
import sys

from app.database import SessionLocal, init_db
from app.models import AdminUser
from app.security import hash_password
from app.services import audit_service


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or update a user")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--role", default="super_admin", choices=["super_admin", "viewer"])
    parser.add_argument(
        "--generate-password",
        action="store_true",
        help="Generate a strong random password and print it once",
    )
    args = parser.parse_args()

    if args.generate_password:
        password = secrets.token_urlsafe(18)
    else:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords do not match.", file=sys.stderr)
            return 1
    if len(password) < 12:
        print("Password must be at least 12 characters.", file=sys.stderr)
        return 1

    init_db()
    db = SessionLocal()
    try:
        user = db.query(AdminUser).filter(AdminUser.username == args.username).first()
        if user:
            user.password_hash = hash_password(password)
            user.role = args.role
            user.is_active = True
            action = "admin_password_reset"
        else:
            user = AdminUser(
                username=args.username,
                password_hash=hash_password(password),
                role=args.role,
                is_active=True,
            )
            db.add(user)
            action = "admin_created"
        db.commit()
        audit_service.log_event(
            db,
            actor="system",
            action=action,
            status="success",
            detail=f"User '{args.username}' role={args.role}",
        )
        print(f"User '{args.username}' saved with role '{args.role}'.")
        if args.generate_password:
            print(f"Password: {password}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
