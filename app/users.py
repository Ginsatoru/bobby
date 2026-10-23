"""Manage Bobby logins.

Usage (from the project folder, with .venv active):
  python -m app.users list
  python -m app.users add <username>
  python -m app.users passwd <username>
  python -m app.users del <username>
  python -m app.users unlock <username>
  python -m app.users admin <username>     (make admin)
  python -m app.users unadmin <username>   (remove admin)
"""
import sys
from getpass import getpass

from app import db
from app.auth import hash_password


def _ask_password() -> str:
    pw = getpass("Password: ")
    if len(pw) < 8:
        sys.exit("Password must be at least 8 characters.")
    if pw != getpass("Repeat password: "):
        sys.exit("Passwords don't match.")
    return pw


def main(args: list[str]) -> None:
    db.init()
    cmd, name = (args + [None, None])[:2]
    if cmd == "list":
        users = db.list_users()
        print("\n".join(u["username"] + (" (admin)" if u["is_admin"] else "") for u in users) or "No users yet.")
        return
    if cmd == "unlock" and name:
        db.clear_login_failures(f"user:{name.lower()}")
        print(f"Unlocked '{name}'.")
        return
    if cmd not in ("add", "passwd", "del", "admin", "unadmin") or not name:
        sys.exit(__doc__)
    user = db.get_user(name)
    if cmd == "add":
        if user:
            sys.exit(f"User '{name}' already exists.")
        db.create_user(name, hash_password(_ask_password()))
        print(f"Added '{name}'.")
    elif not user:
        sys.exit(f"No user '{name}'.")
    elif cmd in ("admin", "unadmin"):
        db.set_admin(user["id"], cmd == "admin")
        print(f"'{name}' is {'now' if cmd == 'admin' else 'no longer'} an admin.")
    elif cmd == "passwd":
        db.set_password(user["id"], hash_password(_ask_password()))
        db.clear_login_failures(f"user:{name.lower()}")
        print(f"Password changed for '{name}'. Their sessions were signed out.")
    elif input(f"Delete '{name}' and all their chats? (y/N) ").lower() == "y":
        db.delete_user(user["id"])
        print(f"Deleted '{name}'.")


if __name__ == "__main__":
    main(sys.argv[1:])