"""One-off: create (or promote) the first admin account for this environment.

There is no public path to becoming admin — /auth/signup always creates
"citizen" — so this script is the only way an admin account gets made. Run it
once per environment (local, staging, production), directly against that
environment's data/auth.db (or AUTH_DATABASE_URL).

Usage:
    python scripts/create_admin.py admin@example.com "Admin Name" "a-strong-password"

If the email already exists, it's promoted to role="admin" instead of erroring.
"""

from __future__ import annotations

import sys

# Ensure the project root is importable when run as a script.
sys.path.insert(0, ".")

from apps.backend.auth import security  # noqa: E402
from apps.backend.auth.db import SessionLocal, init_db  # noqa: E402
from apps.backend.auth.models import User  # noqa: E402


def main() -> None:
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(1)
    email, name, password = sys.argv[1].strip().lower(), sys.argv[2], sys.argv[3]

    init_db()
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            user = User(name=name, email=email, hashed_password=security.hash_password(password), role="admin")
            db.add(user)
            print(f"Created admin account: {email}")
        else:
            user.role = "admin"
            print(f"Promoted existing account to admin: {email}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
