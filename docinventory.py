import os
import platform
import posixpath
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

    def open_shelf(self):
        import shelve
        mkdirp(os.path.dirname(self.shelf_path))
        # return shelve.open(self.gindex_path)
        return closing(shelve.open(self.shelf_path))


def read_inventory(fp, url):
    """
    Read Sphinx inventory file from URL.
    """
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

    def open_shelf(self, shelf=None):
        if shelf is not None:
            return donothing(shelf)
        else:
            return self.ds.open_shelf()

    def download(self, url):
        invurl = posixpath.join(url, 'objects.inv')
        with closing(urllib2.urlopen(invurl)) as fp:
            invdata = read_inventory(fp, url)
        return invdata

    def inventory_names(self, invdata):
        names = set()
        for domain in invdata.values():
            names.update(domain)
        return names

    def add_url(self, url, shelf=None):
        url = posixpath.join(url, '')  # normalize
        with self.open_shelf(shelf) as shelf:
            if url not in shelf:
                shelf[url] = invdata = self.download(url)
                global_index = shelf.get('global_index', {})
                for name in self.inventory_names(invdata):
                    global_index.setdefault(name, set()).add(url)
                shelf['global_index'] = global_index

    def inventory_topics(self, invdata, name):
        for (doctype, domain) in invdata.items():
            match = domain.get(name)
            if match:
                yield Topic(doctype, *match)

    def lookup(self, name, shelf=None):
        with self.open_shelf(shelf) as shelf:
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
