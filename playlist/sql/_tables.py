import contextlib
import copy
import functools
import itertools
import logging
import pprint
import threading
import typing

import sqlalchemy  # NOQA

from playlist.core import config, const, lib, logger


class DBTablesMeta(type):
    _lock = threading.RLock()

    def __get_key(cls, db: const.DB) -> typing.Tuple[str, const.DB]:
        if db.region:
            host = lib.get_region_host()
        else:
            host = lib.get_host()

        return host, db

    def __call__(cls, db: const.DB) -> 'DBTables':
        key = cls.__get_key(db)
        cls.__instances: typing.Dict[typing.Tuple[str, const.DB], 'DBTables']
        with DBTablesMeta._lock:
            try:
                instances = cls.__instances
            except AttributeError:
                instances = cls.__instances = {}
            try:
                return instances[key]
            except KeyError:
                instances[key] = super().__call__(db)
                return instances[key]


class DBTables(metaclass=DBTablesMeta):
    def __init__(self, name: str) -> None:
        self.name = name
        self._lock = threading.RLock()
        self.__tables: typing.Dict[str, typing.Any] = {}

    @property
    def conn(self):
        from playlist.sql import conn
        return conn[self.name]

    def gen_cols(
        self,
        columndefs: typing.Sequence[typing.Mapping[str, typing.Any]],
        add_name: bool=False
    ) -> typing.Generator[str, None, None]:
        for coldef in columndefs:
            if coldef['type'] not in {
                'Integer',
                'String',
                'DateTime',
                'Interval',
                'Float',
                'Boolean',
                'LargeBinary'
            }:
                raise RuntimeError(
                    ' '.join((
                        f"Invalid type: {coldef['type']} for",
                        f"Column {coldef['name']}"
                    ))
                )

            col_args = []
            col_params = {}
            col_doc = 'Column('

            if add_name:
                col_args.append(repr(coldef['name']))
                col_doc = f"{col_doc}, coldef['name']"

            col_doc = f"{col_doc}{coldef['type']}"

            col_args.append(
                f"sqlalchemy.{coldef['type']}()"
            )

            # Sets a column as a primary key.
            with contextlib.suppress(KeyError):
                col_params['primary_key'] = repr(coldef['primary_key'])
                col_doc = f"col_doc, primary_key={coldef['primary_key']!r}"

            # Sets a column to be nullable.
            try:
                col_params['nullable'] = repr(coldef['nullable'])
                col_doc = f"{col_doc}, nullable={coldef['nullable']!r}"

            except KeyError:
                col_doc = f'{col_doc}, nullable=False'

            # Usually, this will be able to be used to define the default value
            # for the column. The "FetchedValue" takes the default straight
            # from the database itself.
            with contextlib.suppress(KeyError):
                if coldef['server_default'] == 'FetchedValue':
                    col_params['server_default'] = \
                        'sqlalchemy.schema.FetchedValue()'
                    col_doc = ', '.join((
                        col_doc,
                        'server_default=FetchedValue'
                    ))
                else:
                    col_params['server_default'] = coldef['server_default']
                    col_doc = ', '.join((
                        col_doc,
                        f"server_default={coldef['server_default']!r}"
                    ))

            # Defines the column as a foreign key, connected to a given
            # table.column
            with contextlib.suppress(KeyError):
                col_args.append(
                    f"sqlalchemy.ForeignKey({coldef['foreign_key']!r})"
                )
                col_doc = f"{col_doc}, foreign_key={coldef['foreign_key']!r}"

            col_doc = ''.join((col_doc, ')'))

            col_params['doc'] = repr(col_doc)

            args = ', '.join(col_args)
            kwargs = ', '.join(
                f'{key}={value}'
                for key, value in col_params.items()
            )
            column_str = f'sqlalchemy.Column({args}, {kwargs})'

            if add_name:
                yield column_str

            else:
                yield f"{coldef['name']} = {column_str}"

    def gen_relations(
        self,
        db: const.DB,
        relationdefs: typing.Sequence[typing.Mapping[str, typing.Any]]
    ) -> typing.Generator[str, None, None]:
        for relationdef in relationdefs:
            # Ensure that a connected table is made.
            if relationdef["ref"] not in self.__tables:
                self.__tables[relationdef["ref"]] = self.__get_table(
                    relationdef["ref"]
                )

            # Sets the table this relationship is made for.
            rel_args = relationdef["ref"]
            rel_params = {}

            # Backrefs are constructed in a special way.
            with contextlib.suppress(KeyError):
                param_iter = itertools.chain(
                    (repr(relationdef["backref"]["name"]),),
                    (
                        f'{key}={value!r}'
                        for key, value in relationdef["backref"].items()
                        if key != 'name'
                    )
                )
                params = ', '.join(param_iter)
                rel_params['backref'] = f'sqlalchemy.orm.backref({params})'

            # Other parameters get set directly here.
            rel_params.update({
                key: repr(value)
                for key, value in relationdef.items()
                if key not in {'ref', 'backref', 'name'}
            })

            kwargs = ', '.join(
                f'{key}={value}'
                for key, value in rel_params.items()
            )
            yield ' = '.join((
                relationdef['name'],
                f"sqlalchemy.orm.relationship({rel_args!r}, {kwargs})"
            ))

    def gen_repr(
        self,
        attrs: typing.Iterator[str]
    ) -> typing.Generator[str, None, None]:
        all_attrs = tuple(attrs)

        # Make the format string to use for the __repr__() method.
        fmt_str = ''.join((
            "    fmt_str = f'<{self.__class__.__name__}(",
            ', '.join((f'{attr}={{self.{attr}!r}}' for attr in all_attrs)),
            ")>'"
        ))

        # Combine the signature with the body.
        yield 'def __repr__(self):'
        yield "    'Returns repr(self).'"
        yield ''
        yield fmt_str
        yield ''
        yield '    return fmt_str'

    def gen_orm_src(
        self,
        table_name: str,
        tabledef: typing.Mapping[str, typing.Any]
    ) -> typing.Generator[str, None, None]:
        fixed_name = table_name.replace('$', '_dlrsgn_')
        base_module = '.'.join(self.__class__.__module__.split('.')[:-1])
        module = f'{base_module}.tables.{self.name}'
        yield 'import sqlalchemy'
        yield ''
        yield 'from playlist.sql import conn, tables'
        yield ''
        yield f'class {fixed_name}(conn.{self.name}.Base):'
        yield ' '.join((
            f"    'SQLAlchemy class defining the {self.name}",
            f"{tabledef['tablename']} table.'"
        ))
        yield ''
        yield f"    __tablename__ = {tabledef['tablename']!r}"
        yield "    __table_args__ = {'keep_existing': True}"
        yield f"    __module__ = '{module}'"

        yield ''

        for col in self.gen_cols(tabledef['columns']):
            yield f'    {col}'

        yield ''

        with contextlib.suppress(KeyError):
            for rel in self.gen_relations(
                self.name,
                tabledef['relationships']
            ):
                yield f'    {rel}'
            yield ''

        for line in self.gen_repr(
            coldef['name']
            for coldef in tabledef['columns']
        ):
            yield f'    {line}'

    def gen_core_src(
        self,
        table_name: str,
        tabledef: typing.Mapping[str, typing.Any]
    ) -> typing.Generator[str, None, None]:
        fixed_name = table_name.replace('$', '_dlrsgn_')
        yield 'import sqlalchemy'
        yield ''
        yield f'{fixed_name} = sqlalchemy.Table('
        yield f'    {table_name!r},'
        yield '    sqlalchemy.schema.MetaData(),'
        for col in self.gen_cols(tabledef['columns'], add_name=True):
            yield f'    {col},'
        yield '    keep_existing=True,'
        yield ')'

    @logger.logged
    def _make_table(self, table_name: str, log: logging.Logger) -> typing.Any:
        with config.db[self.name][table_name] as table_config:
            tabledef = copy.deepcopy(table_config)

        try:
            table_src = '\n'.join([
                line
                for line in self.gen_orm_src(table_name, tabledef)
            ])

        except KeyError:
            table_src = '\n'.join([
                line
                for line in self.gen_core_src(table_name, tabledef)
            ])

        log_lines = (
            '/~~~~~ Table Definition Created ~~~~~\\',
            f'playlist.sql.tables.{self.name}.{table_name}',
            '|~~~~~~~~~~~~~~~ FROM ~~~~~~~~~~~~~~~|',
            pprint.pformat(copy.deepcopy(tabledef)),
            '|~~~~~~~~~~~~~~~~ TO ~~~~~~~~~~~~~~~~|',
            table_src,
            '\\~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~/',
        )
        log.generated('\n'.join(log_lines))

        exec(table_src)
        table = locals()[table_name.replace('$', '_dlrsgn_')]

        with self.conn.get_engine() as engine:
            table.__table__.create(engine, checkfirst=True)

        return table

    def __get_table(self, name: str) -> typing.Any:
        with self._lock:
            try:
                table = self.__tables[name]
            except KeyError:
                while True:
                    with contextlib.suppress(RuntimeError):
                        for subclass in self.conn.Base.__subclasses__():
                            if subclass.__name__ == name:
                                table = subclass

                                break
                        else:
                            table = self._make_table(name)

                        with self.conn.get_engine() as engine:
                            if not engine.has_table(name):
                                table.__table__.create(
                                    engine,
                                    checkfirst=True
                                )
                        self.__tables[name] = table
                        break

            with self.conn.get_engine() as engine:
                table.__table__.create(engine, checkfirst=True)
            return table

    def __getattr__(self, name: str) -> typing.Any:
        return self.__get_table(name)

    def __getitem__(self, name: str) -> typing.Any:
        return self.__get_table(name)

    def __repr__(self) -> str:
        name_iter = config.db[self.name].keys()

        with self._lock:
            table_iter = (
                (name, self.__tables.get(name, config.NotLoaded))
                for name in name_iter
            )
            tables = ', '.join(
                f'{name!r}: {value!r}'
                for name, value in table_iter
            )
        return ' '.join((
            f'<DBTables(db={self.name!r}),',
            f'tables={{{tables}}}>'
        ))


class MainTablesConfig(config.Base):
    def __init__(self) -> None:
        super().__init__(
            attrs=(
                {
                    'name': 'trackdb',
                    'func': functools.partial(DBTables, name='trackdb'),
                    'doc': 'The sqlite trackdb database tables.',
                }
            )
        )

    def __reduce__(self) -> typing.Tuple[
        type,
        typing.Tuple,
        typing.Dict[str, typing.Any]
    ]:
        """Prepare class for pickling."""
        return (MainTablesConfig, (), self.__getstate__())
