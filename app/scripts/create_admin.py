"""Bootstrap (or promote) a platform super-admin — the only way an admin is made.

The ``/admin`` panel never creates admins itself; this one-off CLI does, against
the configured database. Run it once after deploying the admin migration:

    python -m app.scripts.create_admin --email you@example.com --name "Your Name"

The password is read from the ``ADMIN_PASSWORD`` env var, or prompted interactively
(never passed as a CLI argument, so it stays out of shell history). If the email
already exists the account is promoted to super-admin (and its password reset only
if one is supplied); otherwise a new family-less admin account is created.

On Fly.io, run it inside the app machine where the DB wallet is already present:

    fly ssh console -a famo -C "python -m app.scripts.create_admin --email ... --name ..."
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import func, select

from app.core.security import hash_password
from app.domains.admin.repository import AdminRepository
from app.domains.users.models import User, UserRole, new_rid

_MIN_PASSWORD = 8


def _read_password() -> str:
    password = os.environ.get("ADMIN_PASSWORD")
    if password:
        return password
    if not sys.stdin.isatty():
        raise SystemExit(
            "No password: set ADMIN_PASSWORD or run interactively to be prompted."
        )
    first = getpass.getpass("Admin password: ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise SystemExit("Passwords do not match.")
    return first


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create or promote a platform super-admin."
    )
    parser.add_argument("--email", required=True, help="Admin login email.")
    parser.add_argument(
        "--name",
        dest="display_name",
        default=None,
        help="Display name (defaults to the email's local part).",
    )
    args = parser.parse_args(argv)

    email = args.email.strip().lower()
    display_name = args.display_name or email.split("@")[0]
    password = _read_password()
    if len(password) < _MIN_PASSWORD:
        raise SystemExit(f"Password must be at least {_MIN_PASSWORD} characters.")

    # Imported here so importing this module doesn't require a DB driver.
    from app.core.database import new_session

    session = new_session()
    try:
        user = session.scalar(
            select(User).where(func.lower(User.email) == email)
        )
        if user is None:
            user = User(
                rid=new_rid(),
                email=email,
                hashed_password=hash_password(password),
                display_name=display_name,
                family_id=None,
                role=UserRole.MEMBER.value,
                is_superadmin=True,
            )
            session.add(user)
            session.flush()
            action, verb = "admin.bootstrap_create", "Created"
        else:
            user.is_superadmin = True
            user.is_deleted = False
            if password:
                user.hashed_password = hash_password(password)
            action, verb = "admin.bootstrap_promote", "Promoted"

        AdminRepository(session).add_audit(
            actor_user_id=user.id,
            action=action,
            target_type="user",
            target_rid=user.rid,
            detail=f"{verb} super-admin via CLI",
        )
        session.commit()
        print(f"{verb} super-admin: {email} (rid={user.rid})")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
