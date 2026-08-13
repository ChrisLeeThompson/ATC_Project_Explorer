# ATC Project Explorer

A desktop GUI for exploring **Thermo Scientific AutoTEM Cryo (ATC)** project
metadata. Open an ATC project and browse each site's statistics, 
parameters, images, and instrument metadata. Global project data is also 
displayed, including site durations and relative site positions.

Built with PySide6. Developed with **AutoScript 4.13**; it runs inside the
AutoScript 4.13 Python environment with no additional packages, or standalone
using the dependencies in [`requirements.txt`](requirements.txt).

## Features

- **Site explorer** — per-site statistics, parameters, and preview images.
- **Image viewer** — browse a site's image directories with previous/next
  navigation, scroll-wheel zoom, opacity cross-fade between images, and 
  an image-metadata tree.
- **Pattern viewer** — view the relative sizes of the patterns used for a site, 
including parameters used for the patterns.
- **Site-position atlas** — a scatter map of site locations with an image
  montage; click a marker to jump to that site.
- **Process-duration charts** — bar charts of per-step durations; click a bar
  to navigate to the corresponding image.
- **Detachable panels** — open a site in its own window. This can be useful for 
comparing results between two or more sites.

## Requirements

- Python 3.11+
- Core: PySide6, numpy, matplotlib
- Optional (recommended): Pillow (image-loading fallback), tifffile (FEI/TFS
  TIFF metadata used for image overlays and the atlas montage)

Minimum versions are listed in [`requirements.txt`](requirements.txt).

## Install

```bash
# from a clone or extracted release of this repository
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux
pip install -r requirements.txt
```

If you are running inside an **AutoScript 4.13** Python environment, these
packages are already available and no install is needed.

## Run

```bash
python atc_project_explorer.py
```

## Download

Packaged source archives are attached to each tagged release on the
[Releases page](https://github.com/ChrisLeeThompson/ATC_Project_Explorer/releases).
Download and extract the ZIP for the version you want, then follow the
**Install** / **Run** steps above.

## License

MIT — see [LICENSE](LICENSE). Copyright © 2026 Christopher Thompson.

## Contact

Questions or suggestions are welcome — reach Chris Thompson on GitHub
([@ChrisLeeThompson](https://github.com/ChrisLeeThompson)).
