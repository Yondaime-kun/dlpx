# dlpx

Universal media downloader wrapper for **yt-dlp** and **gallery-dl**, with built-in search.

Available as a **CLI tool** and a **mobile app** (Android APK via Flet).

## Features

- **yt-dlp** integration – smart format picking, interactive format selection, download
- **gallery-dl** integration – preview gallery items, export links, batch download
- **Search** – search jable.tv (via scrapling) and YouTube (via yt-dlp) directly from the CLI or interactive mode
- **Batch mode** – process multiple URLs from a file with parallel workers
- **Profiles & config** – JSON config with profiles, cookie/proxy overrides
- **Archive** – skip already-downloaded URLs
- **Doctor** – check tool availability and environment health
- **Installable launcher** – `dlpx` command (user / termux / system scope)
- **Mobile app** – Android APK built with Flet, supports all architectures (arm64-v8a, armeabi-v7a, x86_64) and old/new devices (API 21+, Android 5.0+)

## Requirements

- Python 3.8+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [gallery-dl](https://github.com/mikf/gallery-dl)

```bash
uv sync
```

Or with pip:

```bash
pip install .
```

## Usage

### CLI

```bash
# Interactive mode
python dlp.py

# Search jable.tv from CLI
python dlp.py --search "query"

# Search YouTube from CLI
python dlp.py --search "query" --search-provider youtube

# Direct URL
python dlp.py https://example.com/video

# Download mode
python dlp.py --download https://example.com/video

# Batch mode
python dlp.py --batch urls.txt --download --workers 4

# Doctor / diagnostics
python dlp.py --doctor

# Run as package
python -m dlpx --help
```

### Mobile App (Flet)

Run the mobile-friendly GUI locally:

```bash
pip install flet yt-dlp requests
python main.py
```

### Building APKs

APKs are automatically built by GitHub Actions on every push to `main` and on tag pushes. You can also trigger a build manually from the Actions tab.

To build locally:

```bash
pip install flet
# Fat APK (all architectures)
flet build apk --product "DLPX" --org "com.dlpx" --project "dlpx"

# Per-architecture APKs
flet build apk --arch arm64-v8a --product "DLPX" --org "com.dlpx" --project "dlpx"
flet build apk --arch armeabi-v7a --product "DLPX" --org "com.dlpx" --project "dlpx"
flet build apk --arch x86_64 --product "DLPX" --org "com.dlpx" --project "dlpx"
```

Built APKs are available as GitHub Actions artifacts and as release assets for tagged versions.

#### Architecture Support

| Architecture | Devices |
|---|---|
| `arm64-v8a` | Modern 64-bit ARM phones (most current devices) |
| `armeabi-v7a` | Older 32-bit ARM phones |
| `x86_64` | x86 tablets, emulators |
| `universal` | Fat APK containing all architectures |

Minimum Android version: **5.0 (API 21)**.

## Tests

```bash
pip install pytest flet requests yt-dlp
python -m pytest tests/ -v
```

## Project Structure

```
dlp.py                 # Thin CLI entry point
main.py                # Flet mobile app entry point
dlpx/
├── __init__.py        # Package init
├── __main__.py        # python -m dlpx entry point
├── cli.py             # Argument parser and main()
├── config.py          # Configuration, defaults, paths, profiles
├── utils.py           # Utility functions and dataclasses
├── install.py         # Install/uninstall launcher
├── history.py         # Readline history management
├── archive.py         # Archive (skip already-downloaded)
├── report.py          # JSON report generation
├── doctor.py          # Doctor, engine detection, 1DM opener
├── yt_dlp.py          # yt-dlp backend
├── gallery_dl.py      # gallery-dl backend
├── search.py          # Search (jable.tv scraper)
├── interactive.py     # Interactive flows and main loop
└── batch.py           # Batch processing
tests/
└── test_app.py        # Tests for the Flet app backend
.github/
└── workflows/
    └── build-apk.yml  # CI workflow for building APKs
```