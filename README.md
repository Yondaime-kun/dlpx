# dlpx

Universal media downloader wrapper for **yt-dlp** and **gallery-dl**, with built-in search.

## Features

- **yt-dlp** integration – smart format picking, interactive format selection, download
- **gallery-dl** integration – preview gallery items, export links, batch download
- **Search** – search jable.tv (via scrapling) and YouTube (via yt-dlp) directly from the CLI or interactive mode
- **Batch mode** – process multiple URLs from a file with parallel workers
- **Profiles & config** – JSON config with profiles, cookie/proxy overrides
- **Archive** – skip already-downloaded URLs
- **Doctor** – check tool availability and environment health
- **Installable launcher** – `dlpx` command (user / termux / system scope)

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

## Project Structure

```
dlp.py                 # Thin entry point
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
```