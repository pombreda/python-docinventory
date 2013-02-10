#!/usr/bin/env python

import os
import platform
import urlparse
import urllib2
import functools
from collections import namedtuple
from contextlib import closing

from sphinx.ext import intersphinx


### Utility

def get_config_directory(appname):
    """
    Get OS-specific configuration directory.

    :type appname: str
    :arg  appname: capitalized name of the application

    """
    if platform.system().lower() == 'windows':
        path = os.path.join(os.getenv('APPDATA') or '~', appname, appname)
    elif platform.system().lower() == 'darwin':
        path = os.path.join('~', 'Library', 'Application Support', appname)
    else:
        path = os.path.join(os.getenv('XDG_CONFIG_HOME') or '~/.config',
                            appname.lower())
    return os.path.expanduser(path)


def mkdirp(path):
    """
    Make directory at `path` if it does not exist.
    """
    if not os.path.isdir(path):
        os.makedirs(path)


def return_as(converter):
    """
    Decorator to convert result of a function.

    It is just a function composition. The following two codes are
    equivalent.

    Using `@return_as`::

        @return_as(converter)
        def generator(args):
            ...

        result = generator(args)

    Manually do the same::

        def generator(args):
            ...

        result = converter(generator(args))

    Example:

    >>> @return_as(list)
    ... def f():
    ...     for i in range(3):
    ...         yield i
    ...
    >>> f()  # this gives a list, not an iterator
    [0, 1, 2]

    """
    def wrapper(generator):
        @functools.wraps(generator)
        def func(*args, **kwds):
            return converter(generator(*args, **kwds))
        return func
    return wrapper


### Data store

class DataStore(object):

    appname = 'DocInventory'

    def __init__(self, base_path=None):
        self.base_path = base_path or get_config_directory(self.appname)
        """
        Root directory for any DocInventory related data files.
        """

        self.cache_path = os.path.join(self.base_path, 'cache')
        self.gindex_path = os.path.join(self.base_path, 'gindex')

    _scheme_port_map = {
        'http': 80,
        'https': 443,
    }

    _port_scheme_map = dict((v, k) for (k, v) in _scheme_port_map.items())

    def local_path(self, url):
        result = urlparse.urlparse(url)
        port = result.port or self._scheme_port_map[result.scheme]
        return os.path.join(self.cache_path,
                            result.scheme, result.netloc, str(port),
                            *result.path.split('/'))

    def url(self, local_path):
        relpath = os.path.relpath(self.base_path, local_path)
        (scheme, domain, port, path) = relpath.split(os.path.sep, 3)
        base = '{0}://{1}'.format(scheme, domain)
        if int(port) not in self._port_scheme_map:
            base += ':' + port
        return urlparse.urljoin(base, path)

    def global_inventory(self):
        import shelve
        # return shelve.open(self.gindex_path)
        return closing(shelve.open(self.gindex_path))


Index = namedtuple('Index', ('url', 'local_path', 'names'))
Document = namedtuple('Document', ('url', 'local_path'))


class DocInventory(object):

    def __init__(self, **kwds):
        self.ds = DataStore(**kwds)
        self._inventory_cache = {}

    def is_cached(self, url):
        return os.path.exists(self.ds.local_path(url))

    def download(self, url):
        path = self.ds.local_path(url)
        mkdirp(os.path.dirname(path))
        with open(path, 'wb') as lf:
            with closing(urllib2.urlopen(url)) as rf:
                lf.write(rf.read())
        return path

    def cached_inventory(self, path, url):
        try:
            inv = self._inventory_cache[path]
        except KeyError:
            inv = self._inventory_cache[path] = self.read_inventory(path, url)
        return inv

    def read_inventory(self, path, url):
        import posixpath
        join = posixpath.join
        with open(path, 'rb') as lf:
            line = lf.readline().rstrip().decode('utf-8')
            if line == '# Sphinx inventory version 1':
                invdata = intersphinx.read_inventory_v1(lf, url, join)
            elif line == '# Sphinx inventory version 2':
                invdata = intersphinx.read_inventory_v2(lf, url, join)
        return invdata

    @return_as(set)
    def inventory_names(self, invdata):
        for dct in invdata.values():
            for name in dct:
                yield name

    def add_url(self, url):
        if not self.is_cached(url):
            path = self.download(url)
            names = self.inventory_names(self.read_inventory(path, url))
            with self.ds.global_inventory() as ginv:
                ginv[url] = Index(url, path, names)

    _global_index = None

    def global_index(self):
        if self._global_index:
            return self._global_index
        self._global_index = global_index = {}  # name => [Document]
        with self.ds.global_inventory() as ginv:
            for index in ginv.values():
                for name in index.names:
                    doc = Document(*index[:2])
                    global_index.setdefault(name, []).append(doc)
        return global_index

    def lookup(self, name):
        for (url, local_path) in self.global_index().get(name, []):
            inv = self.cached_inventory(local_path, url)
            for dct in inv.values():
                match = dct.get(name)
                if match:
                    yield match[2]


def run_add(url):
    docinv = DocInventory()
    docinv.add_url(url)


def run_list(name):
    docinv = DocInventory()
    for url in docinv.lookup(name):
        print(url)


def run_browse(name):
    import webbrowser
    docinv = DocInventory()
    for url in docinv.lookup(name):
        webbrowser.open(url)


def main(args=None):
    import argparse
    parser = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    subparsers = parser.add_subparsers()

    parser_add = subparsers.add_parser(
        'add', description='')
    parser_add.add_argument('url')
    parser_add.set_defaults(func=run_add)

    parser_list = subparsers.add_parser(
        'list', description='')
    parser_list.add_argument('name')
    parser_list.set_defaults(func=run_list)

    parser_browse = subparsers.add_parser(
        'browse', description='')
    parser_browse.add_argument('name')
    parser_browse.set_defaults(func=run_browse)

    ns = parser.parse_args(args=args)
    applyargs = lambda func, **kwds: func(**kwds)
    applyargs(**vars(ns))


if __name__ == '__main__':
    main()
