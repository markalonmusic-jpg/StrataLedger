"""Resolve company file paths from the registry, refusing anything outside the installation folder."""
import os

import config
from modules.services.errors import ValidationError


def resolve_company_path(registry_path):
    """Absolute, real path for a company_registry.database_file_path value.

    A relative path is joined to config.BASE_PROJECT_DIR (read at call time). The
    result must lie inside that folder, otherwise ValidationError.
    """
    base = os.path.realpath(config.BASE_PROJECT_DIR)
    candidate = registry_path if os.path.isabs(registry_path) else os.path.join(base, registry_path)
    resolved = os.path.realpath(candidate)
    try:
        inside = os.path.commonpath([os.path.normcase(base), os.path.normcase(resolved)]) == os.path.normcase(base)
    except ValueError:  # different drives on Windows
        inside = False
    if not inside:
        raise ValidationError("The company file is outside the installation folder")
    return resolved


def same_file(a, b):
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
