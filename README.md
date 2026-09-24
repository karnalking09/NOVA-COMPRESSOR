@'

\# NOVA COMPRESSOR



NOVA COMPRESSOR is a Windows desktop file and folder compression application built with Python, Tkinter, TkinterDnD2, and Zstandard.



\## Version



1.0.0



\## Features



\- File compression using Zstandard

\- File decompression

\- Folder compression to `.tar.zst`

\- Folder archive decompression

\- FAST, BALANCED, and MAXIMUM compression profiles

\- Progress tracking

\- Compression speed and ETA display

\- Drag-and-drop input

\- Operation queue

\- Recent operation history

\- Compression analytics

\- SHA-256 integrity verification

\- ZSTD archive validation

\- Output conflict handling

\- Operation cancellation

\- File and folder information

\- Persistent application settings

\- Dark desktop UI



\## Compression Profiles



| Profile | Zstandard Level | Purpose |

|---|---:|---|

| FAST | 1 | Faster processing |

| BALANCED | 5 | General-purpose compression |

| MAXIMUM | 19 | Higher compression effort |



\## Requirements



\- Windows

\- Python 3

\- Zstandard

\- TkinterDnD2



Runtime dependencies are listed in `requirements.txt`.



Build dependency:



`requirements-build.txt`



\## Installation



Create and activate a virtual environment:



```powershell

python -m venv .venv

.\\.venv\\Scripts\\Activate.ps1

