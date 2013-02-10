import os
import platform
import urllib2
import functools
from collections import namedtuple
from contextlib import closing, contextmanager


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


@contextmanager
def donothing(thing):
    yield thing


### Data store

class DataStore(object):

    appname = 'DocInventory'

    def __init__(self, base_path=None):
        self.base_path = base_path or get_config_directory(self.appname)
        """
        Root directory for any DocInventory related data files.
        """

        self.shelf_path = os.path.join(self.base_path, 'shelf')

    def open_shelf(self, shelf=None):
        import shelve
        mkdirp(os.path.dirname(self.shelf_path))
        if shelf:
            return donothing(shelf)
        else:
            # return shelve.open(self.gindex_path)
            return closing(shelve.open(self.shelf_path))


def read_inventory(fp, url):
    """
    Read Sphinx inventory file from URL.
    """
    import posixpath
    from sphinx.ext import intersphinx
    join = posixpath.join
    line = fp.readline().rstrip().decode('utf-8')
    if line == '# Sphinx inventory version 1':
        invdata = intersphinx.read_inventory_v1(fp, url, join)
    elif line == '# Sphinx inventory version 2':
        invdata = intersphinx.read_inventory_v2(fp, url, join)
    return invdata


Topic = namedtuple(
    'Topic', ('type', 'project', 'version', 'location', 'display'))


class DocInventory(object):

    def __init__(self, **kwds):
        self.ds = DataStore(**kwds)

    def download(self, url, shelf=None):
        with closing(urllib2.urlopen(url)) as fp:
            invdata = read_inventory(fp, url)
        with self.ds.open_shelf(shelf) as shelf:
            shelf[url] = invdata
        return invdata

    @return_as(set)
    def inventory_names(self, invdata):
        for dct in invdata.values():
            for name in dct:
                yield name

    def add_url(self, url, shelf=None):
        with self.ds.open_shelf(shelf) as shelf:
            if url not in shelf:
                invdata = self.download(url, shelf=shelf)
                global_index = shelf.get('global_index', {})
                for name in self.inventory_names(invdata):
                    global_index.setdefault(name, set()).add(url)
                shelf['global_index'] = global_index

    def inventory_topics(self, invdata, name):
        for (doctype, dct) in invdata.items():
            match = dct.get(name)
            if match:
                yield Topic(doctype, *match)

    def lookup(self, name, shelf=None):
        with self.ds.open_shelf(shelf) as shelf:
            for url in shelf.get('global_index', {}).get(name):
                for topic in self.inventory_topics(shelf[url], name):
                    yield topic


def run_add(url):
    docinv = DocInventory()
    docinv.add_url(url)


def run_list(name):
    docinv = DocInventory()
    for topic in docinv.lookup(name):
        print(topic.location)


def run_browse(name):
    import webbrowser
    docinv = DocInventory()
    for topic in docinv.lookup(name):
        webbrowser.open(topic.location)


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
