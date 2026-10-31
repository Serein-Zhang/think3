#!/usr/bin/env python3
"""Local, explicitly invoked improvement tracker. Python 3.10+, standard library only."""

from __future__ import annotations

import argparse
import errno
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4


APPLICATION_ID = 0x54484B33  # THK3
SCHEMA_VERSION = 2
SUPPORTED_SCHEMA_VERSIONS = (1, SCHEMA_VERSION)
STATUSES = ("proposed", "implemented", "verified", "withdrawn")
ALLOWED_TRANSITIONS = {
    "proposed": {"implemented", "withdrawn"},
    "implemented": {"verified", "withdrawn"},
    "verified": {"withdrawn"},
    "withdrawn": set(),
}
ADD_FIELDS = ("key", "title", "scope", "action", "basis", "trigger", "success")
ITEM_COLUMNS = (
    "id", *ADD_FIELDS, "supersedes", "status", "revision", "created_at",
    "updated_at", "verification_evidence",
)
EVENT_COLUMNS = (
    "id", "item_id", "kind", "from_status", "to_status", "revision", "note",
    "evidence", "created_at",
)
SCHEMA = (
    """CREATE TABLE items (
        id TEXT PRIMARY KEY NOT NULL,
        key TEXT NOT NULL UNIQUE,
        title TEXT NOT NULL,
        scope TEXT NOT NULL,
        action TEXT NOT NULL,
        basis TEXT NOT NULL,
        trigger TEXT NOT NULL,
        success TEXT NOT NULL,
        supersedes TEXT REFERENCES items(id),
        status TEXT NOT NULL CHECK (status IN
            ('proposed','implemented','verified','withdrawn')),
        revision INTEGER NOT NULL CHECK (revision >= 1),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        verification_evidence TEXT
    )""",
    """CREATE TABLE events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id TEXT NOT NULL REFERENCES items(id),
        kind TEXT NOT NULL CHECK (kind IN ('created','transitioned','observed')),
        from_status TEXT,
        to_status TEXT NOT NULL,
        revision INTEGER NOT NULL,
        note TEXT NOT NULL,
        evidence TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(item_id, revision)
    )""",
    "CREATE INDEX events_by_item ON events(item_id, id)",
)


class TrackerError(Exception):
    def __init__(self, code: str, message: str, exit_code: int = 1):
        super().__init__(message)
        self.code = code
        self.exit_code = exit_code


def emit(value: dict, stream=None) -> None:
    print(json.dumps(value, ensure_ascii=False, allow_nan=False), file=stream or sys.stdout)


class JsonParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise TrackerError("invalid_arguments", message, 2)

    def print_help(self, file=None) -> None:
        emit({"help": self.format_help()}, stream=file)


def skill_version() -> str:
    """Read the version from the bundled entrypoint, without a YAML dependency."""
    text = (Path(__file__).resolve().parents[1] / "SKILL.md").read_text(encoding="utf-8")
    front = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.S)
    in_metadata = False
    if front:
        for line in front.group(1).splitlines():
            if line.rstrip() == "metadata:":
                in_metadata = True
                continue
            if in_metadata and line and not line[0].isspace():
                break
            if in_metadata and line.startswith("  version:"):
                value = line.split(":", 1)[1].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                if re.fullmatch(r"\d+\.\d+\.\d+", value):
                    return value
                break
    raise TrackerError("invalid_skill_metadata", "SKILL.md must declare metadata.version as major.minor.patch.")


def version_info() -> dict:
    return {"name": "think3", "version": skill_version(), "schema_version": SCHEMA_VERSION}


class VersionAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        emit(version_info())
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    parser = JsonParser(description=__doc__)
    parser.add_argument("--version", action=VersionAction, nargs=0,
                        help="Report the bundled skill and database schema versions without opening a store.")
    parser.add_argument("--store", help="Explicit path to a project SQLite database (required).")
    commands = parser.add_subparsers(dest="command", required=True, parser_class=JsonParser)
    for name in ("init", "migrate", "add", "list", "show", "history", "transition", "observe", "export"):
        command = commands.add_parser(name)
        # Accept --store before or after the command without replacing a global value.
        command.add_argument("--store", default=argparse.SUPPRESS)
        if name == "add":
            for field in ADD_FIELDS:
                command.add_argument("--" + field, required=True)
            command.add_argument("--supersedes")
        elif name == "list":
            command.add_argument("--status", choices=STATUSES)
            command.add_argument("--scope")
            command.add_argument("--trigger")
        elif name in ("show", "history", "transition", "observe"):
            command.add_argument("id", nargs="?" if name == "history" else None)
            if name in ("transition", "observe"):
                if name == "transition":
                    command.add_argument("--to", dest="status", required=True, choices=STATUSES)
                command.add_argument("--expected-revision", type=int, required=True)
                command.add_argument("--note", required=True)
                command.add_argument("--evidence", required=name == "observe")
    return parser


def nonempty(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise TrackerError("invalid_arguments", f"{name} must be nonempty.", 2)
    return value.strip()


def store_path(value: str | None) -> Path:
    nonempty(value, "--store")
    # A quoted filesystem path may legitimately start or end with whitespace.
    path = Path(value).expanduser().resolve()
    homes = [Path.home() / ".codex"]
    if os.environ.get("CODEX_HOME"):
        homes.append(Path(os.environ["CODEX_HOME"]))
    protected = [Path(__file__).resolve().parents[1]]
    protected.extend(home / name for home in homes for name in ("memories", "memories_v2"))
    for root in protected:
        root = root.expanduser().resolve()
        if path == root or root in path.parents:
            raise TrackerError("protected_store", "Store records in the project, outside the skill and Codex memories directories.", 2)
    return path


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def database_schema_version(db: sqlite3.Connection) -> int:
    return db.execute("PRAGMA user_version").fetchone()[0]


def validate_database(db: sqlite3.Connection) -> None:
    marker = db.execute("PRAGMA application_id").fetchone()[0]
    version = database_schema_version(db)
    if marker != APPLICATION_ID:
        raise TrackerError("invalid_store", "The file is not a think3 tracker database; it was not modified.")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise TrackerError("unsupported_schema", f"Unsupported schema version {version}; supported versions are 1 and {SCHEMA_VERSION}.")
    for table, expected in (("items", ITEM_COLUMNS), ("events", EVENT_COLUMNS)):
        actual = tuple(row["name"] for row in db.execute(f"PRAGMA table_info({table})"))
        if actual != expected:
            raise TrackerError("invalid_store", f"Invalid {table} schema; the database was not modified.")


def validate_file_identity(path: Path) -> None:
    # SQLite can recover a hot journal before the first PRAGMA query. Read the
    # stable application marker without SQLite so a foreign file stays untouched.
    # https://www.sqlite.org/fileformat.html#application_id
    with path.open("rb") as source:
        header = source.read(100)
    if (len(header) != 100 or header[:16] != b"SQLite format 3\x00"
            or int.from_bytes(header[68:72], "big") != APPLICATION_ID):
        raise TrackerError("invalid_store", "The file is not a think3 tracker database; it was not modified.")


def needs_read_recovery(exc: BaseException, path: Path) -> bool:
    if not isinstance(exc, sqlite3.OperationalError):
        return False
    code = getattr(exc, "sqlite_errorcode", None)
    if code is not None:
        return code == getattr(sqlite3, "SQLITE_READONLY_ROLLBACK", 776)
    # Python 3.10 does not expose SQLite's extended error code. Keep its
    # fallback narrow: the read needs a write and a rollback journal exists.
    return (str(exc) == "attempt to write a readonly database"
            and Path(str(path) + "-journal").is_file())


@contextmanager
def connect(path: Path, *, write: bool = False, validate: bool = True):
    if not path.is_file():
        raise TrackerError("store_not_found", "Store does not exist or is not a file. Run init with an explicit project path first.")
    if validate:
        validate_file_identity(path)
    mode = "rw" if write else "ro"
    db = sqlite3.connect(path.as_uri() + "?mode=" + mode, uri=True, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        if validate:
            validate_database(db)
        yield db
        db.execute("COMMIT")
    except BaseException as exc:
        if db.in_transaction:
            db.execute("ROLLBACK")
        if not write and needs_read_recovery(exc, path):
            raise TrackerError(
                "recovery_required",
                "The existing tracker needs rollback recovery before it can be read. "
                "Run init with the same --store path, then retry this read. "
                "Do not delete the database or its journal; init preserves committed records.",
            ) from exc
        raise
    finally:
        db.close()


def get_item(db: sqlite3.Connection, item_id: str) -> dict:
    row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise TrackerError("item_not_found", f"No item exists with id {item_id!r}.")
    return dict(row)


def events(db: sqlite3.Connection, item_id: str | None = None) -> list[dict]:
    if item_id is not None:
        get_item(db, item_id)
        rows = db.execute("SELECT * FROM events WHERE item_id = ? ORDER BY id", (item_id,))
    else:
        rows = db.execute("SELECT * FROM events ORDER BY id")
    return [dict(row) for row in rows]


def initialize(path: Path) -> dict:
    if path.exists():
        with connect(path, write=True) as db:
            return {"store": str(path), "schema_version": database_schema_version(db), "created": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    # Only publish a fully committed, closed database. A failed or interrupted
    # creation must not occupy the final path with an unusable empty file.
    with tempfile.TemporaryDirectory(prefix=".think3-init-", dir=path.parent) as directory:
        staged = Path(directory) / "ledger.sqlite3"
        staged.touch(exist_ok=False)
        with connect(staged, write=True, validate=False) as db:
            for statement in SCHEMA:
                db.execute(statement)
            db.execute(f"PRAGMA application_id = {APPLICATION_ID}")
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            validate_database(db)
        try:
            if os.name == "nt":
                # Windows rename always refuses an existing destination.
                os.rename(staged, path)
            else:
                # POSIX rename could overwrite it; a hard link publishes
                # atomically without replacing another process's store.
                os.link(staged, path)
        except FileExistsError:
            with connect(path, write=True) as db:
                return {"store": str(path), "schema_version": database_schema_version(db), "created": False}
        except OSError as exc:
            if os.name != "nt" and exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP, errno.ENOSYS, errno.EPERM}:
                raise TrackerError(
                    "unsupported_filesystem",
                    "This location cannot atomically publish a new ledger without replacing an existing file. "
                    "Choose a local filesystem that supports hard links, or keep the project's existing text records. "
                    "This operation did not publish a ledger.",
                ) from exc
            raise
    return {"store": str(path), "schema_version": SCHEMA_VERSION, "created": True}


def migrate_store(path: Path) -> dict:
    """Upgrade an existing ledger only on this explicit, transactional request."""
    with connect(path, write=True) as db:
        previous_version = database_schema_version(db)
        if previous_version == SCHEMA_VERSION:
            return {"store": str(path), "schema_version": previous_version, "migrated": False}

        # Dropping a referenced table can cascade-delete or null out rows in
        # an external table even when its replacement uses the same event IDs.
        # Reject such extensions before touching the schema, including empty
        # referencing tables; a transaction alone does not prevent this loss.
        tables = [row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        for table in tables:
            identifier = table.replace('"', '""')
            for foreign_key in db.execute(f'PRAGMA foreign_key_list("{identifier}")'):
                if foreign_key["table"].casefold() == "events":
                    raise TrackerError(
                        "unsupported_migration",
                        "An additional foreign key references events. This migration does not support that "
                        "database extension; the schema and records were not changed. "
                        "Keep the backup and use a migration that preserves the external dependency.",
                    )

        # The supported legacy schema has the same columns, but its CHECK
        # constraint admits only created/transitioned events. Rebuild the table
        # without changing old rows, event IDs, or the AUTOINCREMENT high-water mark.
        sequence = db.execute("SELECT seq FROM sqlite_sequence WHERE name = 'events'").fetchone()
        event_objects = [row["sql"] for row in db.execute(
            "SELECT sql FROM sqlite_master WHERE tbl_name = 'events' "
            "AND type IN ('index', 'trigger') AND sql IS NOT NULL ORDER BY type, name"
        )]
        db.execute(SCHEMA[1].replace("CREATE TABLE events (", "CREATE TABLE events_v2 (", 1))
        columns = ", ".join(EVENT_COLUMNS)
        db.execute(f"INSERT INTO events_v2 ({columns}) SELECT {columns} FROM events ORDER BY id")
        db.execute("DROP TABLE events")
        db.execute("ALTER TABLE events_v2 RENAME TO events")
        for statement in event_objects:
            db.execute(statement)
        db.execute("CREATE INDEX IF NOT EXISTS events_by_item ON events(item_id, id)")
        if sequence is not None:
            updated = db.execute(
                "UPDATE sqlite_sequence SET seq = MAX(seq, ?) WHERE name = 'events'", (sequence[0],)
            )
            if updated.rowcount == 0:
                db.execute("INSERT INTO sqlite_sequence (name, seq) VALUES ('events', ?)", (sequence[0],))

        # Keep this last so any error rolls back the whole schema change as well
        # as the copied rows. Do not use executescript, which commits implicitly.
        db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        validate_database(db)
        return {
            "store": str(path), "schema_version": SCHEMA_VERSION,
            "from_schema_version": previous_version, "migrated": True,
        }


def add_item(path: Path, args: argparse.Namespace) -> dict:
    values = {field: nonempty(getattr(args, field), "--" + field) for field in ADD_FIELDS}
    values["supersedes"] = nonempty(args.supersedes, "--supersedes") if args.supersedes is not None else None
    with connect(path, write=True) as db:
        existing = db.execute("SELECT * FROM items WHERE key = ?", (values["key"],)).fetchone()
        if existing is not None:
            item = dict(existing)
            if any(item[field] != value for field, value in values.items()):
                raise TrackerError("key_conflict", "This key already exists with different add parameters; use a new key for a distinct item.")
            return {"item": item, "created": False}
        if values["supersedes"] is not None:
            prior = get_item(db, values["supersedes"])
            if prior["status"] != "withdrawn":
                raise TrackerError("invalid_supersedes", "A superseded item must already be withdrawn.")
        timestamp = now()
        item = {
            "id": uuid4().hex, **values, "status": "proposed", "revision": 1,
            "created_at": timestamp, "updated_at": timestamp, "verification_evidence": None,
        }
        columns = ", ".join(ITEM_COLUMNS)
        placeholders = ", ".join("?" for _ in ITEM_COLUMNS)
        db.execute(f"INSERT INTO items ({columns}) VALUES ({placeholders})", tuple(item[column] for column in ITEM_COLUMNS))
        db.execute(
            "INSERT INTO events (item_id, kind, from_status, to_status, revision, note, evidence, created_at) VALUES (?, 'created', NULL, 'proposed', 1, ?, ?, ?)",
            (item["id"], "Item created.", values["basis"], timestamp),
        )
        return {"item": item, "created": True}


def transition_item(path: Path, args: argparse.Namespace) -> dict:
    item_id = nonempty(args.id, "ID")
    note = nonempty(args.note, "--note")
    evidence = nonempty(args.evidence, "--evidence") if args.evidence is not None else None
    if args.expected_revision < 1:
        raise TrackerError("invalid_arguments", "--expected-revision must be a positive integer.", 2)
    if args.status in ("implemented", "verified") and evidence is None:
        raise TrackerError("evidence_required", f"Transition to {args.status} requires nonempty --evidence.", 2)
    with connect(path, write=True) as db:
        previous = get_item(db, item_id)
        if previous["revision"] != args.expected_revision:
            raise TrackerError("revision_conflict", f"Expected revision {args.expected_revision}, but current revision is {previous['revision']}. Reload before making a new decision.")
        if args.status not in ALLOWED_TRANSITIONS[previous["status"]]:
            raise TrackerError("invalid_transition", f"Transition from {previous['status']} to {args.status} is not allowed.")
        timestamp = now()
        revision = previous["revision"] + 1
        verification_evidence = evidence if args.status == "verified" else previous["verification_evidence"]
        updated = db.execute(
            "UPDATE items SET status = ?, revision = ?, updated_at = ?, verification_evidence = ? WHERE id = ? AND revision = ?",
            (args.status, revision, timestamp, verification_evidence, item_id, args.expected_revision),
        )
        if updated.rowcount != 1:
            raise TrackerError("revision_conflict", "The item changed concurrently; reload before making a new decision.")
        db.execute(
            "INSERT INTO events (item_id, kind, from_status, to_status, revision, note, evidence, created_at) VALUES (?, 'transitioned', ?, ?, ?, ?, ?, ?)",
            (item_id, previous["status"], args.status, revision, note, evidence, timestamp),
        )
        return {"item": get_item(db, item_id), "changed": True}


def observe_item(path: Path, args: argparse.Namespace) -> dict:
    """Append evidence without implying that an item's decision has changed."""
    item_id = nonempty(args.id, "ID")
    note = nonempty(args.note, "--note")
    evidence = nonempty(args.evidence, "--evidence")
    if args.expected_revision < 1:
        raise TrackerError("invalid_arguments", "--expected-revision must be a positive integer.", 2)
    with connect(path, write=True) as db:
        if database_schema_version(db) < SCHEMA_VERSION:
            raise TrackerError(
                "migration_required",
                "Appending observations requires schema version 2. "
                "Back up the existing ledger, then run migrate with the same --store path. "
                "Other commands continue to support this schema version 1 ledger.",
            )
        previous = get_item(db, item_id)
        if previous["revision"] != args.expected_revision:
            raise TrackerError("revision_conflict", f"Expected revision {args.expected_revision}, but current revision is {previous['revision']}. Reload before making a new decision.")
        timestamp = now()
        revision = previous["revision"] + 1
        updated = db.execute(
            "UPDATE items SET revision = ?, updated_at = ? WHERE id = ? AND revision = ?",
            (revision, timestamp, item_id, args.expected_revision),
        )
        if updated.rowcount != 1:
            raise TrackerError("revision_conflict", "The item changed concurrently; reload before making a new decision.")
        db.execute(
            "INSERT INTO events (item_id, kind, from_status, to_status, revision, note, evidence, created_at) VALUES (?, 'observed', ?, ?, ?, ?, ?, ?)",
            (item_id, previous["status"], previous["status"], revision, note, evidence, timestamp),
        )
        return {"item": get_item(db, item_id), "changed": True}


def read_store(path: Path, args: argparse.Namespace) -> dict:
    with connect(path) as db:
        if args.command == "show":
            return {"item": get_item(db, nonempty(args.id, "ID"))}
        if args.command == "history":
            return {"events": events(db, nonempty(args.id, "ID") if args.id is not None else None)}
        if args.command == "export":
            return {
                "generator": {"name": "think3", "version": skill_version()},
                "schema_version": database_schema_version(db),
                "items": [dict(row) for row in db.execute("SELECT * FROM items ORDER BY created_at, id")],
                "events": events(db),
            }
        conditions, parameters = [], []
        if args.status is not None:
            conditions.append("status = ?")
            parameters.append(args.status)
        if args.scope is not None:
            conditions.append("scope = ?")
            parameters.append(args.scope)
        if args.trigger is not None:
            conditions.append("instr(trigger, ?) > 0")
            parameters.append(args.trigger)
        where = " WHERE " + " AND ".join(conditions) if conditions else ""
        return {"items": [dict(row) for row in db.execute("SELECT * FROM items" + where + " ORDER BY created_at, id", parameters)]}


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        path = store_path(args.store)
        if args.command == "init":
            result = initialize(path)
        elif args.command == "migrate":
            result = migrate_store(path)
        elif args.command == "add":
            result = add_item(path, args)
        elif args.command == "transition":
            result = transition_item(path, args)
        elif args.command == "observe":
            result = observe_item(path, args)
        else:
            result = read_store(path, args)
        emit(result)
        return 0
    except TrackerError as exc:
        emit({"error": {"code": exc.code, "message": str(exc)}}, stream=sys.stderr)
        return exc.exit_code
    except (sqlite3.Error, OSError, ValueError) as exc:
        code = "database_error" if isinstance(exc, sqlite3.Error) else "filesystem_error"
        emit({"error": {"code": code, "message": str(exc)}}, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())
