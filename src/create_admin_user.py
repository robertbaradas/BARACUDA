from __future__ import annotations

import argparse
import getpass
import sys

from src.auth_client import AuthError, sign_up


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an initial Supabase admin/owner user.")
    parser.add_argument("--email", required=True, help="Email for the admin account")
    parser.add_argument("--username", required=True, help="Display username")
    parser.add_argument("--password", help="Password (prompted if omitted)")
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")

    try:
        session, user_id = sign_up(args.email, password, args.username)
    except AuthError as exc:
        print(f"Failed to create admin user: {exc}")
        return 1

    print(f"Admin user created. User ID: {user_id}")
    if session and getattr(session, 'access_token', None):
        print("Session created successfully; you can now log in via the app.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
