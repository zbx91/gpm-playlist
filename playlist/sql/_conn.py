"""
Encapsulates the implementation of the :py:mod:`playlist.sql.conn` module.

This provides a clean separation of implementation and interface.
Generally speaking, importing this module should not be necessary, but rather
the :py:mod:`playlist.sql.conn` module should be imported instead.

**********
Module API
**********

.. autosummary::
    :nosignatures:

    DBConnection
    MainConnectionConfig
"""
__all__ = (
    'DBConnection',
    'MainConnectionConfig',
)

import contextlib
import functools
import inspect
import logging
import threading
import typing

import sqlalchemy
import sqlalchemy.orm
import sqlalchemy.ext.baked
import sqlalchemy.ext.declarative

from playlist.core import const, config, logger


def get_connect_string() -> str:
    """
    Build the connection string for a database.

    Returns:
        str: The connection string used by
        :py:func:`sqlalchemy.create_engine` to connect to the database.

    """

    with config.settings as settings:
        path = const.BasePath.DATA.value
        path.mkdir(parents=True, exist_ok=True)
        db_path = path / settings.db.file

        connect_string = f'{settings.db.driver}{db_path.as_posix()}'

        with contextlib.suppress(AttributeError):
            if settings.db.params:
                connect_string += '?' + '&'.join((
                    '='.join((key, repr(value)))
                    for key, value in settings.db.params.items()
                ))

    return connect_string


class SQLSession:
    """
    Implements a context manager to handle SQLAlchemy sessions.

    This fully encapsulates a session as an atomic transaction, and if
    anything causes the transaction to fail, it will roll back all changes.

    Note:
        This is usable as both a synchronous and an asynchronous context
        manager.
    """

    def __init__(
        self,
        connection: 'DBConnection'
    ) -> None:
        """
        Initialize the SQLSession object.

        Args:
            sessionmaker (sqlalchemy.orm.session.sessionmaker): The
                :py:class:`sqlalchemy.orm.session.Session` factory to produce
                sessions with. This is expected to already be tied to a
                particular engine.
        """
        self.connection = connection
        self.__lock = threading.RLock()

    @property
    def _engine_cm(self) -> 'DBEngine':
        self.__engine_cm: 'DBEngine'
        with self.__lock:
            try:
                return self.__engine_cm
            except AttributeError:
                self.__engine_cm = self.connection.engine
                return self.__engine_cm

    def __enter__(self) -> sqlalchemy.orm.session.Session:
        """Enter synchronous context manager."""
        with self.__lock:
            self.session: sqlalchemy.orm.session.Session
            try:
                return self.session
            except AttributeError:
                self.engine = self._engine_cm.__enter__()
                sessionmaker = sqlalchemy.orm.sessionmaker(bind=self.engine)
                self.session = sessionmaker()
                return self.session

    @logger.logged
    def __exit__(
        self,
        exc_type: typing.Optional[type],
        exc_value: typing.Optional[BaseException],
        tb: typing.Any,
        *,
        log: logging.Logger,
    ) -> None:
        """Exit synchronous context manager."""
        with self.__lock:
            if exc_type is None:
                self.session.commit()
            else:
                log.error(f'Error found: [{exc_type.__name__}] {exc_value}')
                log.error(f'connection.Base = {self.connection.Base}')
                self.session.rollback()
            self._engine_cm.__exit__(exc_type, exc_value, tb)
            del self.session
            del self.engine


class SessionChecker:
    """
    Checks if a callable has been assigned a session or not.

    It works both synchronously and asynchronously. If a session was not
    found, it adds a session. This works as a context manager.

    This is the core implementation of the function :py:func:`check_session`.

    References:
        :py:func:`check_session`,
        :py:func:`sessionizer`,
    """

    def __init__(
        self,
        sessionmanager: SQLSession,
        bargs: inspect.BoundArguments
    ) -> None:
        """
        Initialize the SessionChecker.

        Args:
            sessionmanager (SQLSession): The SQLSession to produce a session
                with when needed.
            kwargs (Dict[str, Any]): The keyword arguments for the function
                being sessionized.
            keyword (str): The name of the keyword argument to check for the
                session.

        """
        self.sessionmanager = sessionmanager
        self.arguments = bargs.arguments

    def __enter__(self) -> typing.MutableMapping[str, typing.Any]:
        """Enter synchronous context manager."""
        self.session: SQLSession
        function_arguments = self.arguments  # NOQA
        try:
            if self.arguments['session'] is None:
                self.session = self.sessionmanager()
                self.arguments['session'] = self.session.__enter__()
        except KeyError:
            self.session = self.sessionmanager()  # type: ignore
            self.arguments['session'] = self.session.__enter__()

        return self.arguments

    def __exit__(
        self,
        exc_type: typing.Optional[type],
        exc_value: typing.Optional[BaseException],
        tb: typing.Any
    ) -> None:
        """Exit synchronous context manager."""
        with contextlib.suppress(AttributeError):
            self.session.__exit__(exc_type, exc_value, tb)
            del self.session


def _get_bargs(
    sig: inspect.Signature,
    args: typing.Tuple[typing.Any, ...],
    kwargs: typing.Dict[str, typing.Any]
) -> inspect.BoundArguments:
    bargs = sig.bind(*args, **kwargs)
    bargs.apply_defaults()
    return bargs


def sessionizer(
    sessionmanager: SQLSession,
    func: typing.Callable
) -> typing.Callable:
    """
    Ensure that a SQLAlchemy session is passed to the given callable.

    It will either inject a SQLAlchemy session object into a callable, or
    allow the parameter to be left alone if the session already exists.  This
    is designed to properly handle generators, coroutines, or regular
    functions automagically. It is implemented to be used in the
    :py:meth:`ConnectionConfig.sessionize` context manager.

    Args:
        sessionmanager (SQLSession): The context manager that handles the
            session gracefully.
        func (Callable): The function/generator that is decorated so it can
            be sessionized.
        keyword (str): The name of the parameter to assign the session object
            to for the function being decorated. Defaults to ``'session'``

    Returns:
        Callable: The decorated function/generator that has been sessionized.

    References:
        :py:func:`check_session`,
        :py:meth:`ConnectionConfig.sessionize`
    """
    sig = inspect.signature(func)
    sig = sig.replace(
        parameters=[
            value
            if key != 'session'
            else value.replace(default=None)
            for key, value in sig.parameters.items()
        ]
    )
    if inspect.isasyncgenfunction(func):  # type: ignore
        raise ValueError('Cannot be used on Asynchronous Generators.')
    elif inspect.iscoroutinefunction(func):
        raise ValueError('Cannot be used on Coroutines.')
    elif inspect.isgeneratorfunction(func):
        def gen_sql_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.Any:
            with SessionChecker(
                sessionmanager,
                _get_bargs(sig, args, kwargs)
            ) as full_arguments:
                func(**full_arguments)  # type: ignore

        ret = gen_sql_wrapper

    else:
        def func_sql_wrapper(
            *args: typing.Tuple[typing.Any, ...],
            **kwargs: typing.Dict[str, typing.Any]
        ) -> typing.Any:
            with SessionChecker(
                sessionmanager,
                _get_bargs(sig, args, kwargs)
            ) as full_arguments:
                return func(**full_arguments)  # type: ignore

        ret = func_sql_wrapper

    ret.__signature__ = sig  # type: ignore

    return functools.wraps(func)(ret)


class DBEngine:
    def __init__(self) -> None:
        self.__lock = threading.RLock()

    def __verify_sqlite_exists(self):

            with config.settings as settings:
                path = const.BasePath.DATA.value
                path.mkdir(parents=True, exist_ok=True)
                dbcache = path / settings.db.file

            if not dbcache.exists():
                with contextlib.suppress(AttributeError):
                    self.__engine.dispose()
                    del self.__engine
                    del self.__counter

    def __repr__(self):
        try:
            connection = repr(self.__engine)
        except AttributeError:
            connection = 'Not Connected'

        return f'<DBEngine()={connection}>'

    def __enter__(self) -> sqlalchemy.engine.Engine:
        self.__engine: sqlalchemy.engine.Engine
        self.__counter: int

        with self.__lock:
            self.__verify_sqlite_exists()
            try:
                self.__counter += 1
                return self.__engine
            except AttributeError:
                connect_string = get_connect_string()
                self.__engine = sqlalchemy.create_engine(connect_string)
                self.__counter = 1
                return self.__engine

    def __exit__(
        self,
        exc_type: typing.Optional[type],
        exc_value: typing.Optional[BaseException],
        tb: typing.Any,
    ) -> None:
        with self.__lock:
            self.__counter -= 1
            if not self.__counter:
                self.__engine.dispose()  # type: ignore
                del self.__engine
                del self.__counter


class DBConnectionMeta(type):
    _lock = threading.RLock()

    def __call__(cls, name: str) -> 'DBConnection':  # type: ignore
        cls.__instance: 'DBConnection'
        with DBConnectionMeta._lock:
            try:
                return cls.__instance
            except AttributeError:
                cls.__instance = super().__call__(name)
                return cls.__instance


class DBConnection(metaclass=DBConnectionMeta):
    """Class defined to manage a database connection."""

    def __init__(
        self,
        name: str
    ) -> None:
        """Initiaize the DBConnection."""
        self.__lock = threading.RLock()
        self.name = name

    @property
    def engine(self) -> DBEngine:
        """
        Get an engine to execute SQLAlchemy code against.

        Returns:
            sqlalchemy.engine.Engine: The engine instance to use.
        """
        try:
            return self.__engine
        except AttributeError:
            self.__engine = DBEngine()
            return self.__engine

    @property  # type: ignore
    def Base(self) -> 'sqlalchemy.ext.declarative.api.Base':
        """
        Declarative Base class for SQLAlchemy table definitions.

        This is unique per database, per host.
        """
        self.__Base: 'sqlalchemy.ext.declarative.api.Base'  # type: ignore
        with self.__lock:
            try:
                return self.__Base
            except AttributeError:
                self.__Base = sqlalchemy.ext.declarative.declarative_base()
                return self.__Base

    def session(self) -> SQLSession:
        """
        Return the context manager to handle construction of a session.

        Example:
            Using in a with statement::

                with local.session() as session:
                    session.query(table).filter(column='value')

        This automatically will create the session, handle transactional begin
        and commit, or will rollback the transaction on a raised exception.
        It also will close the session when the block is completed, returning
        the resources from the session back to the connection pool.

        Returns:
            SQLSession: A SQLAlchemy session context manager.

        """
        return SQLSession(self)

    def sessionize(
        self
    ) -> typing.Callable:
        """
        Decorator for injecting a session into the decorated callable.

        This is able to be used on functions, generators, and coroutines.

        Examples:
            Sessionize a function::

                @conn.local.sessionize
                def get_value(key, session=None):
                    return session.query(table.value).filter(key=key).one()

            Calling the function without specifying the ``session`` parameter
            automatically creates the session::

                print(get_value('test'))

            Or, it can be called passing a session to use, allowing for
            multiple function calls to share the same session::

                with conn.remote.session() as session:
                    print(get_value('test2', session=session))
                    print(get_value('test3', session=session))

        Args:
            func (Callable): The function, generator, or coroutine to
                decorate.

        Returns:
            Callable: The decorated function, generator, or coroutine.
        """
        def sessionize_this(func: typing.Callable) -> typing.Callable:
            return sessionizer(self.session, func)
        return sessionize_this

    def __repr__(self) -> str:
        """String representation of the DBConnection object."""
        return f'<DBConnection(name={self.name!r}), engine={{{self.engine}}}>'


class MainConnectionConfig(config.Base):
    """Class designed to manage the database connectors for the system."""

    def __init__(self) -> None:
        """Initialize the MainConnectionConfig."""
        super().__init__(
            attrs=(
                {
                    'name': 'trackdb',
                    'func': functools.partial(DBConnection, name='trackdb'),
                    'doc': 'The Track DB'
                },
                {
                    'name': 'bakery',
                    'func': sqlalchemy.ext.baked.bakery,
                    'doc': 'SQLAlchemy baked queries access point.',
                },
            )
        )

    def __reduce__(self) -> typing.Tuple[
        type,
        typing.Tuple,
        typing.Dict[str, typing.Any]
    ]:
        """Prepare class for pickling."""
        return (MainConnectionConfig, (), self.__getstate__())
