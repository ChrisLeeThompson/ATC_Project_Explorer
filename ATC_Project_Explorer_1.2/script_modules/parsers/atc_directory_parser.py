"""
ATC Directory Parser

Module handles discovering the directory structure and image
files within an AutoTEM Cryo (ATC) project. ATC projects have
a fixed top-level layout:

    ATC_Project_Root/
    ├── ProjectData.dat
    ├── Statistics.txt
    └── Sites/
        ├── Lamella (4)/
        │   ├── DCImages/
        │   ├── LamellaEvaluationImages/
        │   └── AutoFocus/          <-- excluded by config
        ├── Lamella (3)/
        └── ...

Site directories live under the ``Sites/`` subdirectory and
their names match the site names in ProjectData.dat exactly.
Within each site directory, the parser walks all subdirectories
(excluding those specified in the config) and collects image
files by extension.

Usage:
    parser = ATCDirectoryParser(
        project_root=Path("/path/to/project"),
        directories_to_exclude=["AutoFocus"],
    )
    site_images = parser.parse()
"""
import logging
import os
from pathlib import Path


logger = logging.getLogger(__name__)


# Supported image file extensions (lowercase, with dot prefix).
IMAGE_EXTENSIONS = {".tif", ".tiff", ".png", ".jpg", ".jpeg"}

# Name of the top-level directory containing site folders.
SITES_DIRECTORY_NAME = "Sites"


class ATCDirectoryParser:

    def __init__(
        self,
        project_root: str | Path,
        directories_to_exclude: list[str] | None = None,
    ):
        """
        Initialize the directory parser.

        :param project_root: Path to the ATC project root directory.
        :param directories_to_exclude: Directory names to skip when
            walking the site subdirectory tree (e.g. ["AutoFocus"]).
        :raises FileNotFoundError: If the project root does not exist.
        """
        self._project_root = Path(project_root)
        if not self._project_root.exists():
            raise FileNotFoundError(
                f"Project root not found: {self._project_root}"
            )
        self._dirs_to_exclude: set[str] = set(
            directories_to_exclude or []
        )
        self._parsed_data: list[dict] | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def parse(self) -> list[dict]:
        """
        Discover site directories and their image files.

        Returns a list of site dictionaries, one per site directory
        found under ``Sites/``. Each dictionary has the structure:

        {
            "SiteName": "Lamella (4)",
            "RelativeSiteDirectoryPath": "Sites/Lamella (4)",
            "ImageDirectories": [
                {
                    "DirectoryName": "DCImages",
                    "RelativeDirectoryPath": "Sites/Lamella (4)/DCImages",
                    "RelativeImagePaths": [
                        "Sites/Lamella (4)/DCImages/image_001.tif",
                        ...
                    ]
                },
                ...
            ]
        }

        :return: List of site directory data dictionaries.
        """
        if self._parsed_data is not None:
            return self._parsed_data

        sites_dir = self._project_root / SITES_DIRECTORY_NAME
        if not sites_dir.exists() or not sites_dir.is_dir():
            logger.warning(
                f"Sites directory not found: {sites_dir}"
            )
            self._parsed_data = []
            return self._parsed_data

        result = []
        for site_dir in sorted(sites_dir.iterdir()):
            if not site_dir.is_dir():
                continue

            site_name = site_dir.name
            relative_site_path = site_dir.relative_to(self._project_root)

            image_directories = self._discover_image_directories(
                site_dir
            )

            result.append({
                "SiteName": site_name,
                "RelativeSiteDirectoryPath": str(relative_site_path),
                "ImageDirectories": image_directories,
            })

        self._parsed_data = result

        # Log summary
        total_dirs = sum(
            len(site["ImageDirectories"]) for site in result
        )
        total_images = sum(
            len(img_dir["RelativeImagePaths"])
            for site in result
            for img_dir in site["ImageDirectories"]
        )
        logger.info(
            f"Directory scan complete: {len(result)} site(s), "
            f"{total_dirs} image director(ies), "
            f"{total_images} image(s)"
        )
        return self._parsed_data

    def get_site_names(self) -> list[str]:
        """
        Return site names discovered from the directory structure.

        :return: List of site name strings.
        """
        data = self._ensure_parsed()
        return [site["SiteName"] for site in data]

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    def _ensure_parsed(self) -> list[dict]:
        """Parse if not already parsed and return the data."""
        if self._parsed_data is None:
            self.parse()
        return self._parsed_data

    def _discover_image_directories(
        self, site_dir: Path
    ) -> list[dict]:
        """
        Walk a site directory tree and collect image directories.

        Recursively walks all subdirectories within the site,
        skipping any directory whose name appears in the exclusion
        set. For each directory that contains at least one image
        file, a record is added to the output.

        :param site_dir: Absolute path to a site directory.
        :return: List of image directory dictionaries.
        """
        image_directories = []

        for dirpath_str, dirnames, filenames in os.walk(site_dir):
            dirpath = Path(dirpath_str)
            # Prune excluded directories in-place so os.walk
            # does not descend into them.
            dirnames[:] = sorted(
                d for d in dirnames
                if d not in self._dirs_to_exclude
            )

            # Collect image files in this directory
            image_files = sorted(
                f for f in filenames
                if Path(f).suffix.lower() in IMAGE_EXTENSIONS
            )

            if not image_files:
                continue

            relative_dir = dirpath.relative_to(self._project_root)
            relative_image_paths = [
                str(relative_dir / img) for img in image_files
            ]

            image_directories.append({
                "DirectoryName": dirpath.name,
                "RelativeDirectoryPath": str(relative_dir),
                "RelativeImagePaths": relative_image_paths,
            })

        return image_directories