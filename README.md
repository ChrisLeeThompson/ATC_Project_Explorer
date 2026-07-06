# ATC Project Explorer

A desktop GUI for exploring **Thermo Scientific AutoTEM Cryo (ATC)** project
metadata. Point it at an ATC project and browse each site's statistics,
parameters, images, and instrument metadata — plus a project-wide
site-position atlas and process-duration charts.

Built with PySide6. Developed against **AutoScript 4.13**; it runs inside the
AutoScript 4.13 Python environment with no additional packages, or standalone
using the dependencies in [`requirements.txt`](requirements.txt).

## Features

- **Site explorer** — per-site statistics, parameters, and preview images.
- **Image viewer** — browse a site's image directories with previous/next
  navigation, opacity cross-fade between images, an image-metadata tree, and a
  clickable image name that reveals the file in your OS file browser.
- **Pattern viewer** — view a site's pattern image with a scale-bar overlay.
- **Site-position atlas** — a scatter map of site locations with an image
  montage; click a marker to jump to that site.
- **Process-duration charts** — bar charts of per-step durations; click a bar
  to navigate to the corresponding image.
- **Detachable panels** — pop a site out into its own window.

## Requirements

- Python 3.11+
- Core: PySide6, numpy, matplotlib
- Optional (recommended): Pillow (image-loading fallback), tifffile (FEI/TFS
  TIFF metadata used for image overlays and the atlas montage)

Exact versions are pinned in [`requirements.txt`](requirements.txt).

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
python atc_project_explorer_1.2.py
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
