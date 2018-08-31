# -*- coding: utf-8 -*-
from distutils.core import setup
import time

_author = 'Mike Burr'
_email = 'mburr@unintuitive.com'
__author__ = '%s <%s>' % (_author, _email)

name = package.__name__

def read(file):
    with open(file, 'r') as f:
        return f.read().strip()

setup(
    name=name,
    version='0.0.1-%s' % time.time(),
    long_description=read('README.md'),
    author=_author,
    author_email=_email,
    provides=[name],
    packages=[name],
)
