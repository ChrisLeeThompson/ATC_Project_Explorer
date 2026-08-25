"""
Validation Utilities

Shared validation functions for verifying ATC project directory
structure.
"""
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


def validate_atc_directory(
    directory_path: Path,
    validation_files: list[str],
) -> tuple[bool, list[str]]:
    """Validate that all required files are present in a directory.

    :param directory_path: Path to the directory to validate.
    :param validation_files: List of filenames that must exist
        in the directory for it to be considered a valid ATC
        project.
    :return: Tuple of ``(is_valid, missing_file_names)``.
        ``is_valid`` is True when all required files are present.
        ``missing_file_names`` is the list of filenames that were
        not found (empty when valid).
    """
    if not validation_files:
        return True, []
    missing = [
        name for name in validation_files
        if not (directory_path / name).exists()
    ]
    return len(missing) == 0, missing