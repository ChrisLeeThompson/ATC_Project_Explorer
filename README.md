# ATC Project Explorer

<!-- Full documentation: https://<site>/scripts/atc_project_explorer/ (enable this link when the site is live) -->

A PySide6 desktop utility for exploring Thermo Scientific AutoTEM Cryo (ATC) project metadata. Open an ATC project and browse each site's statistics, parameters, images, and instrument metadata, along with global project data such as site durations and relative site positions. The project information helps when developing ATC templates, troubleshooting lamella production, and understanding how ATC makes lamellae.

## Features

- **Site explorer** with per-site statistics, parameters, and preview images.
- **Image viewer** that browses a site's image directories with previous/next navigation, scroll-wheel zoom, opacity cross-fade between images, and an image-metadata tree.
- **Pattern viewer** showing the relative sizes of the patterns used for a site along with their parameters.
- **Site-position atlas** with a scatter map of site locations and an image montage; click a marker to open that site.
- **Process-duration charts** of per-step durations; click a bar to open that site.
- **Detachable panels** to open a site in its own window for comparing two or more sites.

## Requirements

- Python 3.11+
- PySide6 6.7.1+
- NumPy 2.2.5+
- Matplotlib 3.8.1+
- Pillow 10.1+
- tifffile 2025.3.13+ (optional; used for FEI/TFS TIFF metadata in image overlays and the atlas montage)

AutoScript is not required. All packages above ship with the AutoScript 4.14 Python environment, where the script is developed and tested, so no extra installation is needed there.

## Installation

1. Download the latest release ZIP from the [Releases page](https://github.com/ChrisLeeThompson/ATC_Project_Explorer/releases).
2. Extract it and copy the script folder to your desired location. The script does not connect to a microscope, so it can be installed on any PC that meets the requirements.
3. If you run the script with the AutoScript Python environment, no packages need to be installed. Otherwise, install them with:

   ```
   pip install -r requirements.txt
   ```

## Running

Run the main module from the script folder:

```
python atc_project_explorer.py
```

The script also runs from the AutoScript Python interpreter or AutoScript Runner.

## Notes

- Tested with ATC 2.4.6.
- Parsing a project writes a temporary consolidated metadata file so later loads are fast. Its name and other options, such as whether the exported JSON is minified, are set in `config_files/ATCProjectExplorerConfig.json`.

## License

MIT, see [LICENSE](LICENSE). Copyright (c) 2026 Christopher Thompson.

The Catbug artwork in `script_assets/` is not covered by the MIT license; see [LICENSE](LICENSE). PySide6 (Qt for Python) is licensed under the LGPLv3 and is used as an unmodified runtime dependency installed from PyPI; it is not distributed with this source.

## Contact

Developed by Chris Thompson with assistance from Anthropic's Claude. Questions and suggestions are welcome: [@ChrisLeeThompson](https://github.com/ChrisLeeThompson) on GitHub.
