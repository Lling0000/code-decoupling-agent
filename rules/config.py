HANDLER_PATH_KEYWORDS = (
    "handler",
    "handlers",
    "controller",
    "controllers",
    "router",
    "routers",
    "route",
    "routes",
)

UTILS_MODULE_KEYWORDS = (
    "utils",
    "common",
    "helper",
    "helpers",
)

UTILS_OVERUSE_THRESHOLD = 5
UTILS_CONSUMER_PACKAGE_THRESHOLD = 3

ENV_RULE_EXCLUDED_PATH_KEYWORDS = (
    "test",
    "tests",
    "conftest.py",
    "config",
    "configs",
    "setting",
    "settings",
    "bootstrap",
    "manage.py",
    "cli",
)

DB_IMPORT_KEYWORDS = (
    "sqlalchemy",
    "flask_sqlalchemy",
    "sqlmodel",
    "django.db",
    "psycopg2",
    "sqlite3",
    "asyncpg",
    "peewee",
    "tortoise",
    "mongoengine",
    "pymongo",
)

DB_IMPORTED_CALL_NAMES = (
    "select",
    "insert",
    "update",
    "delete",
    "create_engine",
    "sessionmaker",
    "scoped_session",
    "session",
    "sessionlocal",
    "asyncsession",
    "sqlalchemy",
    "sqlmodel",
    "declarative_base",
    "mongodbclient",
    "connect",
    "cursor",
)

DB_OPERATION_METHODS = (
    "execute",
    "query",
    "commit",
    "rollback",
    "add",
    "delete",
    "insert",
    "update",
    "filter",
    "where",
    "get",
    "save",
    "find",
    "find_one",
    "insert_one",
    "update_one",
    "bulk_save_objects",
    "bulk_insert_mappings",
)

DB_CALL_KEYWORDS = (
    "db.session",
    "model.query",
    *tuple(f".{name}" for name in DB_OPERATION_METHODS),
    *DB_IMPORTED_CALL_NAMES,
)

DB_ROOT_NAME_HINTS = (
    "db",
    "session",
    "engine",
    "connection",
    "conn",
    "cursor",
    "client",
    "collection",
    "queryset",
)

GLOBAL_STATE_IGNORED_NAMES = (
    "__all__",
    "__version__",
    "__author__",
    "__doc__",
    "__annotations__",
)

GLOBAL_STATE_MUTATION_METHODS = (
    "append",
    "extend",
    "insert",
    "remove",
    "pop",
    "popitem",
    "clear",
    "update",
    "setdefault",
    "set",
    "put",
    "register",
    "add",
    "discard",
    "__setitem__",
)
