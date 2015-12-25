# -*- coding: utf-8 -*-
try:
    from pkgutil import extend_path
    __path__ = extend_path(__path__, __name__)
except ImportError:
    from pkg_resources import declare_namespace
    declare_namespace(__name__)
