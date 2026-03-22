"""
Project Data Parser

Module handles parsing the ProjectData.dat XML file from an
AutoTEM Cryo (ATC) project directory. The ProjectData.dat file
is an XML file with root element <AutoTEM> containing instrument
information, project metadata, and per-site data including
parameters, stage positions, and workflow activity details.

The parser converts the XML into a structured Python dictionary.
The <n> tag used by ATC for names is normalized to "Name" in the
output dictionary.

Usage:
    parser = ProjectDataParser(Path("path/to/ProjectData.dat"))
    data = parser.parse()
    site_names = parser.get_site_names()
"""
import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path


logger = logging.getLogger(__name__)


class ProjectDataParser:

    def __init__(self, file_path: str | Path):
        """
        Initialize the parser with the path to a ProjectData.dat file.

        :param file_path: Path to the ProjectData.dat file.
        :raises FileNotFoundError: If the file does not exist.
        """
        self._file_path = Path(file_path)
        if not self._file_path.exists():
            raise FileNotFoundError(
                f"ProjectData.dat not found: {self._file_path}"
            )
        self._parsed_data: dict | None = None

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def parse(self) -> dict:
        """
        Parse the ProjectData.dat XML file and return a structured
        dictionary containing the full project data.

        The returned dictionary has top-level keys matching the XML
        root children (typically "Instrument" and "Project").

        :return: Dictionary of parsed project data.
        :raises ET.ParseError: If the XML cannot be parsed.
        """
        if self._parsed_data is not None:
            return self._parsed_data

        xml_content = self._read_file()
        root = ET.fromstring(xml_content)

        result = {}
        for child in root:
            tag = self._normalize_tag(child.tag)
            result[tag] = self._xml_to_dict(child)

        self._parsed_data = result

        # Log summary
        site_names = self.get_site_names()
        project_name = self.get_project_name()
        logger.info(
            f"Parsed ProjectData.dat: project='{project_name}', "
            f"{len(site_names)} site(s)"
        )
        return self._parsed_data

    def get_project_name(self) -> str:
        """
        Extract the project name from the parsed data.

        :return: Project name string, or empty string if not found.
        """
        data = self._ensure_parsed()
        project = data.get("Project", {})
        if isinstance(project, dict):
            return project.get("Name", "")
        return ""

    def get_site_names(self) -> list[str]:
        """
        Extract the list of site (lamella) names from the parsed data.

        :return: List of site name strings in the order they appear
                 in the XML.
        """
        sites = self._get_sites()
        names = []
        for site in sites:
            name = site.get("Name", "")
            if name:
                names.append(name)
        return names

    def get_sites(self) -> list[dict]:
        """
        Return the list of parsed site dictionaries.

        :return: List of site data dictionaries.
        """
        return self._get_sites()

    def get_instrument_info(self) -> dict:
        """
        Extract instrument information from the parsed data.

        :return: Dictionary of instrument fields (SystemType,
                 ServerVersion, etc.), or empty dict if not found.
        """
        data = self._ensure_parsed()
        instrument = data.get("Instrument", {})
        return instrument if isinstance(instrument, dict) else {}

    def get_project_info(self) -> dict:
        """
        Extract project-level information (excluding the Sites list).

        Returns fields such as Name, Version, TimeCreated,
        ProjectStarted, ProjectEnded, etc.

        :return: Dictionary of project-level fields.
        """
        data = self._ensure_parsed()
        project = data.get("Project", {})
        if not isinstance(project, dict):
            return {}
        # Return a copy without the Sites key
        return {
            key: value for key, value in project.items()
            if key != "Sites"
        }

    # -----------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------

    def _ensure_parsed(self) -> dict:
        """Parse if not already parsed and return the data."""
        if self._parsed_data is None:
            self.parse()
        return self._parsed_data

    def _read_file(self) -> str:
        """
        Read the ProjectData.dat file content.

        Uses utf-8-sig encoding to handle the BOM (byte order mark)
        that is present in ATC-generated XML files.

        :return: File content as a string.
        """
        with open(self._file_path, "r", encoding="utf-8-sig") as f:
            return f.read()

    @staticmethod
    def _normalize_tag(tag: str) -> str:
        """
        Normalize XML tag names.

        ATC uses <n> as the tag for name fields. This is mapped
        to "Name" for clarity in the output dictionary.

        :param tag: Raw XML tag name.
        :return: Normalized tag name.
        """
        if tag == "n":
            return "Name"
        return tag

    def _xml_to_dict(self, element: ET.Element) -> dict | str | None:
        """
        Recursively convert an XML element into a Python dictionary.

        Conversion rules:
        - Leaf elements (no children) return their text content as
          a string, or None if empty.
        - Elements with children return a dictionary mapping
          normalized tag names to their parsed values.
        - If multiple children share the same tag, they are grouped
          into a list.
        - XML attributes are included in the dictionary.

        :param element: An XML Element to convert.
        :return: Parsed value (dict, str, or None).
        """
        if element is None:
            return None

        result = {}

        # Include XML attributes
        if element.attrib:
            result.update(element.attrib)

        # Process child elements
        children = list(element)
        if children:
            # Group children by normalized tag
            child_groups: dict[str, list] = defaultdict(list)
            for child in children:
                tag = self._normalize_tag(child.tag)
                child_data = self._xml_to_dict(child)
                if child_data is not None:
                    child_groups[tag].append(child_data)

            for tag, values in child_groups.items():
                if len(values) == 1:
                    result[tag] = values[0]
                else:
                    result[tag] = values
        else:
            # Leaf element — return text content
            text = element.text.strip() if element.text else None
            if text:
                if not result:
                    return text
                result["_text"] = text

        return result if result else None

    def _get_sites(self) -> list[dict]:
        """
        Navigate the parsed data to retrieve the list of site
        dictionaries.

        Handles the case where "Sites" may contain a single Site
        (parsed as a dict) or multiple Sites (parsed as a list).

        :return: List of site dictionaries, or empty list.
        """
        data = self._ensure_parsed()
        project = data.get("Project", {})
        if not isinstance(project, dict):
            return []

        sites = project.get("Sites", {})
        if isinstance(sites, dict):
            # Single site — Sites contains a "Site" key
            site = sites.get("Site")
            if site is None:
                return []
            if isinstance(site, list):
                return site
            return [site]
        if isinstance(sites, list):
            return sites
        return []