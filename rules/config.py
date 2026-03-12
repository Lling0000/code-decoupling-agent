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

# DB methods split by confidence to reduce false positives.
# HIGH: almost certainly a DB operation regardless of context.
DB_HIGH_CONFIDENCE_METHODS = (
    "execute",
    "commit",
    "rollback",
    "bulk_save_objects",
    "bulk_insert_mappings",
    "insert_one",
    "update_one",
    "find_one",
    "executemany",
    "fetchone",
    "fetchall",
    "fetchmany",
)

# LOW: could be a DB operation but also common on non-DB objects (lists, dicts, caches).
# These are only flagged when stronger context is present.
DB_LOW_CONFIDENCE_METHODS = (
    "add",
    "get",
    "filter",
    "save",
    "find",
    "where",
    "query",
    "delete",
    "insert",
    "update",
)

DB_OPERATION_METHODS = DB_HIGH_CONFIDENCE_METHODS + DB_LOW_CONFIDENCE_METHODS

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
    "collection",
    "queryset",
)

# "client" removed from DB_ROOT_NAME_HINTS — too generic, causes false positives.
# DB signals on "client" objects are only flagged when using high-confidence methods.
DB_GENERIC_ROOT_HINTS = (
    "client",
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

# Safe methods that should NOT be treated as mutations even on global objects.
GLOBAL_STATE_SAFE_METHODS = frozenset((
    "copy",
    "keys",
    "values",
    "items",
    "union",
    "intersection",
    "difference",
    "symmetric_difference",
    "issubset",
    "issuperset",
    "isdisjoint",
    "__len__",
    "__contains__",
    "__iter__",
    "__repr__",
    "__str__",
    "__getitem__",
    "__hash__",
    "count",
    "index",
    "get",
    "freeze",
    "frozen",
))

# Thresholds for the oversized file/class rule (RULE_F).
OVERSIZED_FILE_LINE_THRESHOLD = 500
OVERSIZED_CLASS_METHOD_THRESHOLD = 15
