from functools import wraps

from flask import abort, redirect, request, session, url_for

from .. import db
from .. import models as m


def current_user():
    from flask import has_request_context

    if not has_request_context():
        return None
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(m.User, uid)


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None or not user.is_active:
            session["_next"] = request.path
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return wrapper


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None or not user.is_active:
                return redirect(url_for("auth.login"))
            if user.role not in roles:
                abort(403)
            return f(*args, **kwargs)

        return wrapper

    return decorator
