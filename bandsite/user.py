from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import db
from .extensions import login_manager


class Member(UserMixin):
    """A band member who can sign in. Wraps a row from the members table."""

    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.instrument = row.get("instrument")
        self.is_admin = bool(row.get("is_admin"))
        self.password_hash = row["password_hash"]

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


def hash_password(password):
    return generate_password_hash(password)


@login_manager.user_loader
def load_member(member_id):
    try:
        row = db.get_member(int(member_id))
    except (TypeError, ValueError):
        return None
    return Member(row) if row else None
