from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from . import store
from .extensions import login_manager


class Member(UserMixin):
    """Logged-in band member, built from a band_member row."""

    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.instrument = row["instrument"]
        self.is_admin = bool(row["is_admin"])
        self._password_hash = row["password_hash"]

    def check_password(self, password):
        return check_password_hash(self._password_hash, password)


def hash_password(password):
    return generate_password_hash(password)


@login_manager.user_loader
def load_user(user_id):
    try:
        row = store.member_by_id(int(user_id))
    except (TypeError, ValueError):
        return None
    return Member(row) if row else None
