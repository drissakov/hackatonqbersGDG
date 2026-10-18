"""Lazy, bounded psycopg connections. Blocking work runs outside the ASGI loop."""

import re
from contextlib import contextmanager
from queue import Empty, LifoQueue
from threading import BoundedSemaphore, Lock

import psycopg
from psycopg.conninfo import conninfo_to_dict
from psycopg.rows import dict_row


class DatabaseUnavailable(Exception):
    """Safe infrastructure error; never contains a driver exception or DSN."""


def schema_name(value: str) -> str:
    if value != "app" and not re.fullmatch(r"test_s01_[a-f0-9]{12}", value):
        raise ValueError("Use app or a generated test_s01_<12 hex digits> schema")
    return value


def connection_options(url: str) -> dict:
    if not url:
        raise DatabaseUnavailable("database_not_configured")
    try:
        options = conninfo_to_dict(url)
    except (psycopg.Error, ValueError):
        raise DatabaseUnavailable("invalid_database_configuration") from None
    host = options.get("host", "")
    if host.endswith(".supabase.com") or host.endswith(".supabase.co"):
        if not host.endswith(".pooler.supabase.com") or options.get("port", "5432") != "5432":
            raise DatabaseUnavailable("supabase_session_pooler_required")
    mode = options.get("sslmode", "require")
    if mode not in {"require", "verify-ca", "verify-full"}:
        raise DatabaseUnavailable("database_tls_required")
    options.update(
        sslmode=mode,
        connect_timeout=5,
        options="-c statement_timeout=5000 -c lock_timeout=3000 "
        "-c idle_in_transaction_session_timeout=10000",
        application_name="qadam-backend",
        prepare_threshold=None,
        row_factory=dict_row,
    )
    return options


class DatabasePool:
    """At most three connections; no new dependency or eager network access.

    A checkout owns one transaction. Success commits, failure rolls back; broken
    connections are discarded. Shutdown and returns synchronize via one lock.
    """

    def __init__(self, url: str, max_size: int = 3):
        if not 1 <= max_size <= 5:
            raise ValueError("Pool size must be between one and five")
        self._url = url
        self._idle = LifoQueue()
        self._slots = BoundedSemaphore(max_size)
        self._lock = Lock()
        self._closed = False

    @contextmanager
    def connection(self):
        if not self._slots.acquire(timeout=5):
            raise DatabaseUnavailable("database_pool_timeout")
        connection = None
        try:
            with self._lock:
                if self._closed:
                    raise DatabaseUnavailable("database_pool_closed")
                try:
                    connection = self._idle.get_nowait()
                except Empty:
                    pass
            if connection is None:
                connection = psycopg.connect(**connection_options(self._url))
            if not connection.pgconn.ssl_in_use:
                connection.close()
                raise DatabaseUnavailable("database_tls_required")
            try:
                yield connection
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        except (psycopg.Error, OSError):
            if connection is not None:
                connection.close()
            raise DatabaseUnavailable("database_operation_failed") from None
        finally:
            if connection is not None:
                with self._lock:
                    if self._closed or connection.closed or connection.broken:
                        connection.close()
                    else:
                        self._idle.put_nowait(connection)
            self._slots.release()

    def close(self):
        with self._lock:
            self._closed = True
            while not self._idle.empty():
                self._idle.get_nowait().close()
