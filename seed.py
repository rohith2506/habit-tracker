"""Seed the database with the two users.

Usage:
    python seed.py             # creates users if missing, default passwords
    python seed.py --reset     # drops & recreates all tables, then seeds
"""
import argparse

from app.db import Base, engine, SessionLocal
from app.models import User
from app.security import hash_password


DEFAULTS = [
    {"username": "rohith",  "display_name": "Rohith",  "color": "blue", "avatar_initial": "R", "timezone": "Europe/Amsterdam", "password": "Hachimi@2510"},
    {"username": "akshaya", "display_name": "Akshaya", "color": "pink", "avatar_initial": "A", "timezone": "Europe/Amsterdam", "password": "Hachimi@2510"},
]


def reset():
    Base.metadata.drop_all(bind=engine)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="Drop all tables first")
    args = parser.parse_args()

    if args.reset:
        print("Dropping tables...")
        reset()

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        created = []
        for spec in DEFAULTS:
            existing = db.query(User).filter(User.username == spec["username"]).first()
            if existing:
                print(f"  user '{spec['username']}' already exists, skipping")
                continue
            user = User(
                username=spec["username"],
                password_hash=hash_password(spec["password"]),
                display_name=spec["display_name"],
                color=spec["color"],
                avatar_initial=spec["avatar_initial"],
                timezone=spec["timezone"],
            )
            db.add(user)
            created.append(spec)

        db.commit()
        for spec in created:
            print(f"  created user '{spec['username']}' (password: {spec['password']})")
        print("Done.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
