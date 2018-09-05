# -*- mode: python; coding: utf-8 -*-
"""re-export `modules.*` and make models (and ORM) usable outside of web framework.

So, if you have django "app" `foo` installed as a package, from anywhere you should be able to

>>> record = foo.db.SomeTable(**kwargs)
>>> record.save()

et cetera.
"""

import django
from .settings import *
from django.conf import settings
from django.db import connections
import atexit
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

settings.configure(DATABASES=DATABASES)
django.setup()

from .models import *

def cleanup():
    logger.info('closing all django database connections for this process')
    connections.close_all()

atexit.register(cleanup)
