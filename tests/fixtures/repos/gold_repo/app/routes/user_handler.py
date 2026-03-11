from sqlalchemy import select


def list_users(session):
    return session.execute(select("users"))
