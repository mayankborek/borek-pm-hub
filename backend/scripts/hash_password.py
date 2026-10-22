"""Print an Argon2 hash of a password, for creating or updating a user with plain SQL.

Run from the backend folder:  python -m scripts.hash_password
(asks for the password without showing it; nothing is stored or sent anywhere)

Example SQL with the printed hash:
  UPDATE users SET password_hash = '<hash>', failed_login_count = 0, locked_until = NULL
  WHERE email = 'someone@example.com';
"""

import getpass

from app.auth.security import hash_password


def main() -> None:
    password = getpass.getpass("Password: ")
    if len(password) < 12:
        raise SystemExit("Use at least 12 characters.")
    if getpass.getpass("Repeat: ") != password:
        raise SystemExit("The passwords do not match.")
    print(hash_password(password))


if __name__ == "__main__":
    main()
