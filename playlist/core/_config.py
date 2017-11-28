"""
Module that encapsulates the implementation of :py:mod:`playlist.core.config`.

This provides a clean separation of implementation and interface. Generally
speaking, importing this module should not be necessary, but rather
:py:mod:`playlist.core.config` should be imported instead.

**********
Module API
**********

.. autosummary::
    :nosignatures:

    BaseConfig
    DictConfig
"""

__all__ = [
    'BaseConfig',
    'DictConfig',
]


import abc
import collections
import collections.abc
import copy
import functools
import itertools
import sys
import types
import typing


class SingletonMeta(type):
    """
    Metaclass used for implementing singletons.

    Used by :py:class:`NotLoadedType`.
    """

    __slots__ = ()

    def __init__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: dict
    ) -> None:
        """
        Initialize the singleton class.

        Args:
            name (str): The name of the class to be constructed.
            bases (Tuple[type]): The bases for the class.
            namespace (dict): The namespace dictionary for the class.

        Keyword Args:
            slots (Tuple[str]): A tuple of names to put in the __slots__
                attribute.
        """
        try:
            cls.__instance: typing.Any
        except AttributeError:
            super().__init__(name, bases, namespace)

    def __call__(
        cls,
        *args: typing.Tuple[typing.Any, ...],
        **kwargs: typing.Dict[str, typing.Any]
    ) -> typing.Any:
        """Handle singleton implementation."""
        try:
            return cls.__instance
        except AttributeError:
            cls.__instance = super().__call__(*args, **kwargs)
            return cls.__instance


class NotLoadedType(metaclass=SingletonMeta):
    """
    Value that a Config object's elements are set to before they get loaded.

    This class doesn't really have any purpose besides being a placeholder
    when a Config element isn't loaded yet. Once the element is loaded, this
    placeholder disappears.
    """

    def __str__(self) -> str:
        """String version of the NotLoadedType object."""
        return 'Not Loaded'

    def __repr__(self) -> str:
        """String representation of the NotLoadedType object."""
        return '<Not Loaded>'

    def __bool__(self) -> bool:
        """Any instance of NotLoadedType is False."""
        return False

    def __hash__(self) -> int:
        """Hash value for the NotLoadedType object."""
        return hash(type(self).__name__)

    def __reduce__(self) -> tuple:
        """Used by pickling."""
        return (NotLoadedType, ())

    def __call__(self):
        """
        Any instance of NotLoadedType cannot be called.

        Raises:
            TypeError: Always, NotLoaded can't be called.
        """
        raise TypeError(
            "'{name}' object is not callable".format(
                name=type(self).__name__
            )
        )


NotLoaded = NotLoadedType()


class ConfigValuesView(
    collections.abc.ValuesView
):
    """View of a config object's values."""

    def __repr__(self) -> str:
        """String represenation of the ConfigValuesView."""
        return ''.join((type(self).__name__, '(', repr(tuple(self)), ')'))


class ConfigKeysView(
    collections.abc.KeysView
):
    """View of a config object's keys."""

    def __repr__(self) -> str:
        """String represenation of the ConfigKeysView."""
        return ''.join((type(self).__name__, '(', repr(set(self)), ')'))


class ConfigItemsView(
    collections.abc.ItemsView
):
    """View of a config object's (key, value) items."""

    def __repr__(self) -> str:
        """String represenation of the ConfigItemsView."""
        return ''.join((type(self).__name__, '(', repr(tuple(self)), ')'))


class ConfigSimpleAttr:
    """
    Simple loaded attribute descriptor for Config objects.

    References:
        :py:class:`ConfigLoadableAttr`
    """

    def __init__(
        self,
        value: typing.Any,
        doc: typing.Optional[str]=None
    ) -> None:
        """
        Initialize the simple attribute.

        Args:
            value (Any): The value for this attribute.
            doc (Optional[str]): The docstring for this attribute.
        """
        self.value = value
        self.__doc__ = getattr(value, '__doc__', doc)

    @property  # type: ignore
    def __doc__(self):
        """Get attribute docstring."""
        return self._my_doc

    @__doc__.setter
    def __doc__(self, doc):
        self._my_doc = doc

    def __get__(self, inst, cls):
        """Get the value of this attribute."""
        return self.value

    def __set__(self, inst, value):
        """
        Unable to set a simple attribute.

        Raises:
            AttributeError: Always, can't set a ConfigSimpleAttr descriptor.
        """
        raise AttributeError("can't set attribute")

    def __delete__(self, inst):
        """
        Unable to delete a simple attribute.

        Raises:
            AttributeError: Always, can't delete a ConfigSimpleAttr descriptor.
        """
        raise AttributeError("can't delete attribute")


class ConfigLoadableAttr:
    """Loadable attribute descriptor for Config objects."""

    def __init__(
        self,
        name: str,
        func: typing.Callable,
        doc: typing.Optional[str]=None
    ) -> None:
        """
        Initialize the loadable attribute.

        Args:
            name (str): The name of the attribute.
            func (Callable): The function to execute to load the attribute
                with.
            doc (Optional[str]): The docstring for this attribute.
        """
        self.name = name
        self.func = func
        if doc is not None:
            self.__doc__ = doc

    @property  # type: ignore
    def __doc__(self):
        """Get attribute docstring."""
        return self._my_doc

    @__doc__.setter
    def __doc__(self, doc):
        self._my_doc = doc

    def _reconfigure(self, inst, cls, ret):
        setattr(
            cls,
            str(self.name),
            ConfigSimpleAttr(ret, doc=self.__doc__)
        )
        inst._attrs_ |= {self.name}
        inst._funcs_ -= {self.name}
        return ret

    def __get__(self, inst, cls):
        """Load the attribute, replace with :py:class:`ConfigSimpleAttr`."""
        ret = self.func()
        ret = self._reconfigure(inst, cls, ret)

        return ret

    def __set__(self, inst, value):
        """
        Unable to set a loadable attribute.

        Raises:
            AttributeError: Always, can't set a ConfigLoadableAttr descriptor.
        """
        raise AttributeError("can't set attribute")

    def __delete__(self, inst):
        """
        Unable to delete a loadable attribute.

        Raises:
            AttributeError: Always, can't delete a ConfigLoadableAttr
                descriptor.
        """
        raise AttributeError("can't delete attribute")


class ConfigSetableAttr:
    """Setable attribute descriptor for Config objects."""

    def __init__(
        self,
        name: str,
        doc: typing.Optional[str]=None,
        preload: bool=True
    ) -> None:
        """
        Initialize the setable attribute.

        Args:
            name (str): The name of the attribute.
            doc (Optional[str]): The docstring for this attribute.
            preload (bool): Automatically load the attribute when set or not.
                Defaults to True.
        """
        self.name = name
        self.preload = preload
        if doc is not None:
            self.__doc__ = doc

    @property  # type: ignore
    def __doc__(self):
        """Get attribute docstring."""
        return self._my_doc

    @__doc__.setter
    def __doc__(self, doc):
        self._my_doc = doc

    def __get__(self, inst, cls):
        """
        Unable to get a setable attribute.

        Raises:
            AttributeError: Always, can't get a ConfigSetableAttr descriptor.
        """
        raise AttributeError(
            "'{typename}' object has no attribute '{name}'".format(
                typename=cls.__name__,
                name=self.name
            )
        )

    def __set__(self, inst, func: typing.Callable):
        """
        Set the attribute.

        If ``preload`` is True, it replaces the attribute with a
        :py:class:`ConfigSimpleAttr, otherwise it replaces it with a
        :py:class:`ConfigLoadableAttr`.

        Args:
            inst: The object instance we are setting the attribute on.
            func (Callable): The function to execute to get the value for
                this attribute.
        """
        if self.preload:
            value = func()
            setattr(
                type(inst),
                str(self.name),
                ConfigSimpleAttr(value, doc=self.__doc__)
            )
            inst._attrs_ |= {self.name}
            inst._setables_ -= {self.name}

        else:
            setattr(
                type(inst),
                str(self.name),
                ConfigLoadableAttr(self.name, func, doc=self.__doc__)
            )
            inst._funcs_ |= {self.name}
            inst._setables_ -= {self.name}

    def __delete__(self, inst):
        """
        Unable to delete a setable attribute.

        Raises:
            AttributeError: Always, can't delete a ConfigSetableAttr
                descriptor.
        """
        raise AttributeError(
            "'{typename}' object has no attribute '{name}'".format(
                typename=type(inst).__name__,
                name=self.name
            )
        )


class ConfigMeta(abc.ABCMeta):
    """Metaclass for BaseConfig and subclasses."""

    @staticmethod
    def config_dir(self):
        """Return dir(self)."""
        my_vars = set(self)
        skips = self._bad_names | my_vars

        yield from (
            attr
            for attr in dir(type(self))
            if (
                attr not in skips and
                not (
                    attr.startswith('_') and
                    not attr.startswith('__') and
                    hasattr(self, attr[1:])
                ) and hasattr(self, attr)
            )
        )

        yield from my_vars

    @classmethod
    def __prepare__(
        metacls,
        name: str,
        bases: typing.Tuple[type, ...],
        *,
        bad_names: typing.Set[str]=None
    ) -> typing.Dict[str, typing.Any]:
        """
        Prepare the Config class for being constructed.

        This sets several attributes that are used by the Config object.

        Args:
            name (str): The name of the class being prepared.
            bases (Tuple[type]): Tuple containing all base classes for the
                class.

        Keyword Args:
            bad_names (Set[str]): Set of attributes, methods, etc. that
                should be excluded from :py:func:`dir`.

        Returns:
            dict: Contains all of the additional attributes to put into the
                namespace dict for the class.
        """
        if bad_names is None:
            bad_names = set()

        return {
            '__dir__': metacls.config_dir,
            '_bad_names': frozenset({
                attr
                if not attr.startswith('__')
                else ''.join(('_', name, attr))
                for attr in bad_names
            } | {
                '_bad_names',
                '__setables',
                '__funcs',
                '__attrs',
                '_setables_',
                '_funcs_',
                '_attrs_'
            } | {
                attr
                for base in bases
                for attr in getattr(base, '_bad_names', ())
            }),
        }

    def __new__(
        cls,
        name: str,
        bases: typing.Tuple[type],
        namespace: dict,
        **kwargs
    ):
        """
        Construct the new Config class.

        Args:
            name (str): The name of the class.
            bases (Tuple[type]): Tuple of all base classes.
            namespace (dict): The namespace dict for the class.
            **kwargs: Not used, hides additional keyword arguments passed to
                :py:meth:`__prepare__`.
        """
        return super().__new__(cls, name, bases, namespace)

    def __init__(
        cls,
        name: str,
        bases: typing.Tuple[type, ...],
        namespace: dict,
        **kwargs
    ) -> None:
        """
        Initialize the new Config class.

        Args:
            name (str): The name of the class.
            bases (Tuple[type]): Tuple of all base classes.
            namespace (dict): The namespace dict for the class.
            **kwargs: Not used, hides additional keyword arguments passed to
                :py:meth:`__prepare__`.
        """
        super().__init__(name, bases, namespace)


def path_query(
    data_structure: typing.Union[
        typing.Sequence[typing.Any],
        typing.Mapping[str, typing.Any]
    ],
    *path
) -> typing.Any:
    """
    Query a path depth-first in the given data structure.

    Args:
        data_structure (Union[Sequence[Any], Mapping[Any]]): The data to
            query.
        *path: The keys and/or indexes to drill down through the data
            strucure with.

    Returns:
        Any: The element in the data structure at the given path.

    Note:
        The parameters that are collected in ``path`` must be viable keys
        and/or indexes.
    """
    ret = data_structure

    for key in path:
        ret = ret[key]

    return ret


class BaseConfig(
    collections.abc.Mapping,
    metaclass=ConfigMeta,
    bad_names={
        '_set_attr',
        '_abc_cache',
        '_abc_negative_cache',
        '_abc_negative_cache_version',
        '_abc_registry',
        '__abstractmethods__',
        '_factory_subclass',
        '__delattr__',
        '__gen_keys',
        '__gen_items',
    }
):
    """Base class for all Config objects."""

    def __new__(cls, *args, **kwargs):
        """
        Construct a new instance.

        This functions like a factory, and will make a dummy subclass of the
        class before sending to :py:meth:`__init__`, in order to ensure that
        properties (attributes) do not bleed across instances of the class.

        Args:
            *args: The positional arguments passed to the constructor.
            **kwargs: The keyword arguments passed to the constructor.

        Returns:
            BaseConfig: The new specialized subclass for this instance.
        """
        if hasattr(cls, '_factory_subclass'):
            return super().__new__(*args, **kwargs)

        else:
            new_cls_name = cls.__name__
            new_cls = type(new_cls_name, (cls,), {
                '__module__': '.'.join((
                    cls.__module__,
                    cls.__name__,
                    'subclass'
                )),
                '_factory_subclass': True,
                '__doc__': '\n'.join((
                    'Factory-generated specialized subclass.'.format(
                        name=cls.__name__
                    ),
                    cls.__doc__ if cls.__doc__ is not None else ''
                ))
            })
            return super().__new__(new_cls)

    def __init__(self, *, attrs: typing.Iterable[dict]) -> None:
        """
        Initialize the BaseConfig.

        This sets up all of the attributes of the newly-constructed
        BaseConfig subclass.

        There are three kinds of attributes that can be defined for a Config
        object: Simple, Loadable, and Setable.  Based on the keys used in an
        attribute's dict, the correct kind of attribute will be chosen. The
        keys to use for the dict are as follows:

        * ``'name'``: The name of the attribute (required).
        * ``'func'``: The function to execute to load an attribute
            (optional). If not included, the attribute will be defined as
            *Setable*, and will need to be explicitly assigned to the
            function that will be used to load it.  The function must be able
            to be executed without passing any parameters to it.
        * ``'doc'``: The docstring to use for the attribute (optional). If
            not given, the docstring will default to
            ``'The {name} attribute.'``
        * ``'preload'``: A boolean that can force an attribute to be loaded
            when the Config object is constructed, rather than waiting until
            the attribute is accessed (optional). Setting this to ``True``
            will cause the attribute to be defined as *Simple*, if the
            ``'func'`` item is included. Setting this to ``False`` (or
            skipping it) will cause the attribute to be defined as
            *Loadable*, if the ``'func'`` item is included. If the
            ``'func'`` item is not included, this will dictate how the
            attribute will be handled *after* it has been set.

        Warning:
            To set an attribute to a value, it must be passed as a
            ``lambda``, i.e.: ``config.data = lambda: 5`` rather than
            ``config.data = 5``.

        Args:
            attrs (Iterable[dict]): All of the attributes to load into the
                Config object.  Each attribute is defined with a dict, all of
                the dicts are placed in the iterable, and processed
                separately.

        References:
            :py:class:`ConfigSimpleAttr`,
            :py:class:`ConfigLoadableAttr`,
            :py:class:`ConfigSetableAttr`
        """
        self.__funcs: frozenset
        self.__attrs: frozenset
        self.__setables: frozenset
        if attrs:
            tuple(map(lambda a: self._set_attr(**a), attrs))

    @property
    def _funcs_(self) -> frozenset:
        try:
            return self.__funcs
        except AttributeError:
            self.__funcs = frozenset()
            return self.__funcs

    @_funcs_.setter
    def _funcs_(self, new_funcs: typing.Iterable) -> None:
        self.__funcs = frozenset(new_funcs)

    @property
    def _attrs_(self) -> frozenset:
        try:
            return self.__attrs
        except AttributeError:
            self.__attrs = frozenset()
            return self.__attrs

    @_attrs_.setter
    def _attrs_(self, new_attrs: typing.Iterable) -> None:
        self.__attrs = frozenset(new_attrs)

    @property
    def _setables_(self) -> frozenset:
        try:
            return self.__setables
        except AttributeError:
            self.__setables = frozenset()
            return self.__setables

    @_setables_.setter
    def _setables_(self, new_setables: typing.Iterable) -> None:
        self.__setables = frozenset(new_setables)

    def _set_attr(
        self,
        name: str,
        func: typing.Optional[typing.Callable]=None,
        doc: typing.Optional[str]=None,
        preload: bool=False
    ) -> None:
        attr: typing.Union[
            ConfigSetableAttr,
            ConfigSimpleAttr,
            ConfigLoadableAttr
        ]
        if doc is None:
            doc = 'The {name} attribute.'.format(name=name)

        if func is None:
            # Setable
            attr = ConfigSetableAttr(name, doc=doc, preload=preload)
            self._funcs_ -= {name}
            self._attrs_ -= {name}
            self._setables_ |= {name}

        elif preload:
            # Loaded
            attr = ConfigSimpleAttr(func(), doc=doc)
            self._funcs_ -= {name}
            self._attrs_ |= {name}
            self._setables_ -= {name}

        else:
            # Loadable
            attr = ConfigLoadableAttr(
                name,
                func,
                doc=doc
            )
            self._funcs_ |= {name}
            self._attrs_ -= {name}
            self._setables_ -= {name}

        setattr(type(self), name, attr)

    def __gen_keys(self) -> typing.Generator[str, None, None]:
        yield from (str(item) for item in sorted(self._attrs_ | self._funcs_))

    def __gen_items(self) -> typing.Generator[
        typing.Tuple[
            str,
            typing.Any
        ],
        None,
        None
    ]:
        yield from (
            (str(key), getattr(self, str(key)))
            for key in self._attrs_
        )
        yield from ((str(key), NotLoaded) for key in self._funcs_)

    def __hash__(self) -> int:
        """The hash value for the Config object."""
        return hash(
            (type(self).__module__, type(self).__qualname__) +
            tuple(self.__gen_keys())
        )

    @property
    def __dict__(  # type: ignore
        self
    ) -> types.MappingProxyType:
        """An immutable dict representation of the Config object."""
        return types.MappingProxyType(self)

    def __contains__(self, key: str) -> bool:  # type: ignore
        """Return key in self."""
        return key in set(self.__gen_keys())

    def __repr__(self) -> str:
        """Return repr(self)."""
        return repr(dict(self.__gen_items()))

    def __getitem__(self, key: str) -> typing.Any:
        """Return self[key]."""
        try:
            return getattr(self, key)

        except AttributeError as e:
            raise KeyError(key) from e

    def __setitem__(self, key: str, value: typing.Any) -> None:
        """Perform self[key] = value."""
        try:
            setattr(self, key, value)

        except AttributeError:
            raise TypeError(
                "'{name}' object does not support item assignment".format(
                    name=type(self).__name__
                )
            )

    def __delitem__(self, key: str) -> None:
        """
        Cannot delete items from Config objects.

        Raises:
            TypeError: Always, don't try deleting items from Config objects.
        """
        raise TypeError(
            "'{name}' object does not support item deletion".format(
                name=type(self).__name__
            )
        )

    def __str__(self) -> str:
        """Return str(self)."""
        return str(dict(self.__gen_items()))

    def __sizeof__(self) -> int:
        """Return sys.getsizeof(self)."""
        return sys.getsizeof(vars(self))

    def __len__(self) -> int:
        """Return len(self)."""
        return len(tuple(self.__gen_keys()))

    def __iter__(self) -> typing.Generator[str, None, None]:
        """Return iter(self)."""
        yield from self.__gen_keys()

    def keys(self) -> ConfigKeysView:
        """Return a set-like view of the Config object's keys."""
        return ConfigKeysView(self)  # type: ignore

    def values(self) -> ConfigValuesView:
        """Return a set-like view of the Config object's values."""
        return ConfigValuesView(self)  # type: ignore

    def items(self) -> ConfigItemsView:
        """Return a set-like view of the Config object's items."""
        return ConfigItemsView(self)  # type: ignore

    def copy(self) -> typing.Any:
        """A shallow copy of D."""
        return copy.copy(self)

    def __copy__(self) -> typing.Any:
        """For use with the :py:func:`copy.copy` function."""
        return copy.copy(dict(self.__gen_items()))

    def get(self, key: str, default: typing.Any=None) -> typing.Any:
        """
        Get the Config object's attribute as a dictionary key.

        Args:
            key (str): The Config object's attribute name, as a string.
            default (Any): The value to use if the Config object does not have
                the given attribute. Defaults to None.

        Returns:
            Any: The vale of the Config object's attribute, or the default
            value if the Config object does not have the given attribute.
        """
        return getattr(self, key, default)

    def __deepcopy__(self, memo: dict) -> typing.Any:
        """
        For use with the :py:func:`copy.deepcopy` function.

        References:
            :py:func:`unpack_element`
        """
        try:
            return memo[id(self)]
        except KeyError:
            memo[id(self)] = unpack_element(self, memo=memo)
            return memo[id(self)]

    @functools.lru_cache(maxsize=128)
    def get_path(self, *path: typing.Tuple[str, ...]) -> typing.Any:
        """
        Do a depth-first query of the Config object.

        Simple method that provides access to sub-elements by listing the
        index/key for each sub element as parameters to this method.

        Example:
            .. code-block:: python

                from playlist.core import config
                test = config.get_path('settings', 'app_db_objowner')

                # is the same as

                test = config['settings']['app_db_objowner']

                # is the same as

                test = config.settings.app_db_objowner

        This is useful for a yaml to get values from some other part of the
        :py:mod:`playlist.core.config` module.

        Example:
            .. code-block:: yaml

                plugin_group_key_values:
                    - ctx_default: >-
                        !!python/object/apply:playlist.core.config.get_path
                        [settings, app_db_objowner]

        Args:
            *path: the indexes/keys, listed as individual parameters, to
            get to the value you are seeking.

        Returns:
            The value at the given location in the config object.
        """
        return path_query(self, *path)

    def __getstate__(self) -> typing.Dict[str, typing.Any]:
        """Used in pickling, stores the state of the Config object."""
        return dict(
            _setables_=self._setables_,
            **{name: getattr(self, name) for name in self._attrs_}
        )

    def __setstate__(self, state: dict) -> None:
        """Used in pickling, restores the state of the Config object."""
        for key, value in state.items():
            if key == '_setables_':
                self._setables_ = value
                for name in value:
                    setattr(type(self), name, ConfigSetableAttr(name))
            else:
                setattr(type(self), key, ConfigSimpleAttr(value))

    @abc.abstractmethod
    def __reduce__(self) -> typing.Tuple[
        type,
        typing.Tuple[
            str,
            typing.Optional[bool],
            typing.Optional[typing.List[dict]],
        ],
        typing.Any
    ]:
        """Used in pickling, defines how to pickle the Config object."""
        pass


def parse_element(elem: typing.Any) -> typing.Any:
    """
    Convert a data structure into a read-only equivalent.

    The primary use-case for this is the
    :py:func:`playlist.core.config.to_config` function, which converts a data
    structure into a Config object.

    The conversion it does is as follows:

    ==================================== ======================
    Original                             Result
    ==================================== ======================
    :py:class:`collections.abc.Mapping`  :py:class:`DictConfig`
    :py:class:`collections.abc.Set`      :py:class:`frozenset`
    :py:class:`collections.abc.Sequence` :py:class:`tuple`
    *anything else*                      *unchanged*
    ==================================== ======================

    Args:
        elem (Any): The data structure or element to be parsed

    Returns:
        Any: The parsed/converted element, as per the table above.

    References:
        :py:func:`playlist.core.config.to_config`
    """
    is_class = isinstance(elem, type)
    is_config = isinstance(elem, BaseConfig)
    is_mapping = isinstance(elem, collections.abc.Mapping)
    is_set = isinstance(elem, collections.abc.Set)
    is_string = isinstance(elem, (str, bytes, bytearray))
    is_sequence = isinstance(elem, collections.abc.Sequence) and \
        not isinstance(elem, tuple)

    if is_class or is_config:
        ret = elem

    elif is_mapping:
        ret = DictConfig(elem)

    elif is_set:
        ret = frozenset(parse_element(value) for value in elem)

    elif not is_string and is_sequence:
        ret = tuple(parse_element(value) for value in elem)

    else:
        ret = elem

    return ret


def unpack_element(
    elem: typing.Any,
    memo: typing.MutableMapping[int, typing.Any]={}
) -> typing.Any:
    """
    Convert a read-only data structure into a mutable equivalent.

    The primary use-cases for this is the
    :py:func:`playlist.core.config.from_config` function and using
    :py:func:`copy.deepcopy` on a Config object.

    The conversion it does is as follows:

    ==================================== ================
    Original                             Result
    ==================================== ================
    :py:class:`collections.abc.Mapping`  :py:class:`dict`
    :py:class:`collections.abc.Set`      :py:class:`set`
    :py:class:`collections.abc.Sequence` :py:class:`list`
    *anything else*                      *unchanged*
    ==================================== ================

    Args:
        elem (Any): The data structure or element to be parsed

    Returns:
        Any: The parsed/converted element, as per the table above.

    References:
        :py:func:`playlist.core.config.from_config`
    """
    try:
        return memo[id(elem)]

    except KeyError:
        is_type = isinstance(elem, type)
        is_mapping = isinstance(elem, collections.abc.Mapping)
        is_set = isinstance(elem, collections.abc.Set)
        is_string = isinstance(elem, (str, bytes, bytearray))
        is_sequence = isinstance(elem, collections.abc.Sequence)

        if is_type:
            ret = elem

        elif is_mapping:
            ret = {
                key: unpack_element(value, memo=memo)
                for key, value in elem.items()
            }

        elif is_set:
            ret = {unpack_element(value, memo=memo) for value in elem}

        elif not is_string and is_sequence:
            ret = [unpack_element(value, memo=memo) for value in elem]

        else:
            ret = elem

        memo[id(elem)] = ret

        return memo[id(elem)]


class DictConfig(BaseConfig):
    """
    Class designed to translate a dictionary into a configuration.

    Note:
        This is primarily used in the :py:func:`parse_element` function, and
        generally is not used directly.
    """

    def __init__(
        self,
        source: dict,
        attrs: typing.Optional[typing.Iterable[dict]]=None
    ) -> None:
        """
        Initialize the DictConfig.

        Args:
            source(dict): The source dict to convert into a DictConfig
                instance.
            extra_attrs (Optional[Iterable[dict]]): Additional attributes to
                add to the Config, following the format of the ``attrs``
                parameter for BaseConfig.
        """
        if attrs is None:
            attrs = ()

        super().__init__(
            attrs=itertools.chain(
                (
                    {
                        'name': key,
                        'func': functools.partial(parse_element, value),
                        'doc': (
                            value.__doc__
                            if hasattr(value, '__doc__')
                            else f'value: {value!r}'
                        ),
                        'preload': True
                    }
                    for key, value in source.items()
                ),
                attrs
            )
        )

    def __reduce__(self) -> typing.Tuple[  # type: ignore
        'DictConfig',
        typing.Tuple[typing.Any],
        dict
    ]:
        """Prepare the DictConfig for pickling."""
        return (  # type: ignore
            DictConfig,
            (copy.deepcopy(self),),
            self.__getstate__()
        )


class MainConfig(DictConfig):
    """Class used to define the ``playlist.core.config`` module."""

    def __init__(
        self,
        attrs: typing.Optional[typing.Iterable[dict]]
    ) -> None:
        """Initialize the MainConfig."""
        source = {
            'Base': BaseConfig,
            'Dict': DictConfig,
            'to_config': parse_element,
            'NotLoaded': NotLoaded
        }

        super().__init__(source=source, attrs=attrs)

    def __reduce__(self) -> typing.Tuple[  # type: ignore
        'MainConfig',
        tuple,
        dict
    ]:
        """Prepare the MainConfig for pickling."""
        return (MainConfig, (), self.__getstate__())  # type: ignore
