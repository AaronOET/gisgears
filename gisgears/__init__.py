"""
GISGEARS - A collection of tools for GIS/hydrology raster and vector analysis.
"""

__version__ = '0.6.5'

__all__ = [
    'describe',
    'showshp',
    'showtable',
    'showtif',
    'showtif2',
    'wsdgen',
    'wsdpyshed',
    'wsdsmooth',
]

import importlib

# Tool modules are imported on first access (PEP 562) rather than here, so
# `import gisgears` and each command only load the heavy libraries they use
# (pysheds alone takes several seconds to import)
_LAZY_MODULES = set(__all__) | {'cli'}


def __getattr__(name):
    if name in _LAZY_MODULES:
        module = importlib.import_module(f'.{name}', __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | _LAZY_MODULES)
