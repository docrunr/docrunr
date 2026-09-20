"""DocRunr local public API."""

from importlib.metadata import PackageNotFoundError, version

from docrunr_api.app import create_app

try:
    __version__ = version("docrunr-api")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__", "create_app"]
