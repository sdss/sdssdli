# encoding: utf-8

from sdsstools import get_package_version


NAME = "sdssdli"

__version__ = get_package_version(path=__file__, package_name=NAME)


from .controller import *
