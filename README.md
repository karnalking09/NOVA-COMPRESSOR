<div align="center">



# 🚀 NOVA COMPRESSOR



### High-Performance Windows File \& Folder Compression Utility



\*\*Powered by Zstandard • SHA-256 Integrity Verification • Drag \& Drop • Compression Analytics\*\*



\[!\[Version](https://img.shields.io/badge/version-1.0.0-blue?style=for-the-badge)](./VERSION)

\[!\[Python](https://img.shields.io/badge/Python-3.14+-yellow?style=for-the-badge\&logo=python\&logoColor=white)](https://www.python.org/)

\[!\[Zstandard](https://img.shields.io/badge/Zstandard-0.25.0-orange?style=for-the-badge)](https://facebook.github.io/zstd/)

\[!\[Platform](https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge\&logo=windows\&logoColor=white)](https://www.microsoft.com/windows)



\[!\[GitHub stars](https://img.shields.io/github/stars/karnalking09/NOVA-COMPRESSOR?style=flat-square)](https://github.com/karnalking09/NOVA-COMPRESSOR/stargazers)

\[!\[GitHub forks](https://img.shields.io/github/forks/karnalking09/NOVA-COMPRESSOR?style=flat-square)](https://github.com/karnalking09/NOVA-COMPRESSOR/network/members)

\[!\[GitHub issues](https://img.shields.io/github/issues/karnalking09/NOVA-COMPRESSOR?style=flat-square)](https://github.com/karnalking09/NOVA-COMPRESSOR/issues)

\[!\[GitHub last commit](https://img.shields.io/github/last-commit/karnalking09/NOVA-COMPRESSOR?style=flat-square)](https://github.com/karnalking09/NOVA-COMPRESSOR/commits/main)



</div>



\---



## 📌 Overview



\*\*NOVA COMPRESSOR\*\* is a Windows desktop application built with Python and Zstandard for file and folder compression workflows.



It provides a graphical interface for:



\- File compression

\- Folder compression

\- File and folder decompression

\- Zstandard archive validation

\- SHA-256 integrity verification

\- FAST / BALANCED / MAXIMUM compression profiles

\- Drag-and-drop workflows

\- Operation queue management

\- Compression analytics

\- Progress, speed, and ETA monitoring

\- Operation cancellation

\- Output conflict handling

\- Persistent application settings

\- Recent operation history

\- Dark desktop interface



\---



## ✨ Feature Matrix



| Feature | Status |

|---|:---:|

| 🚀 Zstandard compression | ✅ |

| 📦 Folder → `.tar.zst` | ✅ |

| 🔄 File decompression | ✅ |

| 📂 Folder decompression | ✅ |

| ⚡ FAST profile | ✅ |

| ⚖️ BALANCED profile | ✅ |

| 🧠 MAXIMUM profile | ✅ |

| 📊 Compression analytics | ✅ |

| 📈 Progress tracking | ✅ |

| 🚄 Speed monitoring | ✅ |

| ⏱️ ETA calculation | ✅ |

| 🖱️ Drag \& Drop | ✅ |

| 📋 Operation queue | ✅ |

| 🕘 Recent operations | ✅ |

| 🔐 SHA-256 verification | ✅ |

| 🧪 ZSTD validation | ✅ |

| 🛑 Operation cancellation | ✅ |

| ⚙️ Persistent settings | ✅ |

| 🔁 Output conflict handling | ✅ |

| 🌑 Dark interface | ✅ |

| 🪟 Windows executable build | ✅ |



\---



## ⚡ Compression Profiles



| Profile | Zstandard Level | Intended Use |

|---|---:|---|

| ⚡ \*\*FAST\*\* | `1` | Faster compression |

| ⚖️ \*\*BALANCED\*\* | `5` | General-purpose compression |

| 🧠 \*\*MAXIMUM\*\* | `19` | Higher compression effort |



> Actual compression ratio and processing time depend on the input data.



\---



## 🔐 Integrity Verification



NOVA COMPRESSOR uses \*\*SHA-256\*\* verification to detect data corruption.



### Regular `.zst` Files



For regular file compression, the integrity sidecar represents the SHA-256 hash of the original decoded data.



```text

Original File

&#x20;    │

&#x20;    ▼

Zstandard Compression

&#x20;    │

&#x20;    ├── archive.zst

&#x20;    │

&#x20;    └── archive.zst.sha256



During validation or decompression, the decoded data can be hashed again and compared with the expected SHA-256 value.



Folder .tar.zst Archives



Folder compression creates a compressed TAR archive:



Folder

&#x20; │

&#x20; ▼

TAR Archive

&#x20; │

&#x20; ▼

Zstandard Compression

&#x20; │

&#x20; ├── folder.tar.zst

&#x20; │

&#x20; └── folder.tar.zst.sha256



For folder .tar.zst validation, the SHA-256 value represents the compressed archive itself.



Validation Rule



Strict validation succeeds only when the calculated hash matches the expected hash.



📊 Compression Analytics



NOVA COMPRESSOR provides runtime information such as:



Input size

Output size

Compression ratio

Space reduction

Processing progress

Current speed

Estimated remaining time

Operation status



Compression results depend on the characteristics of the input data.



Highly repetitive data can compress dramatically, while already-compressed or random data may provide little or no size reduction.



🖱️ Desktop Workflow

┌─────────────────────────┐

│       Select Input      │

│    File / Folder / D\&D  │

└────────────┬────────────┘

&#x20;            │

&#x20;            ▼

┌─────────────────────────┐

│  Select Compression     │

│ FAST / BALANCED / MAX   │

└────────────┬────────────┘

&#x20;            │

&#x20;            ▼

┌─────────────────────────┐

│    Compression Queue    │

└────────────┬────────────┘

&#x20;            │

&#x20;            ▼

┌─────────────────────────┐

│  Zstandard Processing   │

└────────────┬────────────┘

&#x20;            │

&#x20;            ▼

┌─────────────────────────┐

│ Progress / Speed / ETA  │

└────────────┬────────────┘

&#x20;            │

&#x20;            ▼

┌─────────────────────────┐

│   SHA-256 Verification  │

└─────────────────────────┘

📦 Supported Workflows

File Compression

file.ext

&#x20;  │

&#x20;  ▼

file.ext.zst

&#x20;  │

&#x20;  ▼

Decompression

&#x20;  │

&#x20;  ▼

file.ext

Folder Compression

MyFolder/

&#x20;  │

&#x20;  ▼

MyFolder.tar.zst

&#x20;  │

&#x20;  ▼

Decompression

&#x20;  │

&#x20;  ▼

MyFolder/

🛠️ Technology Stack

Technology	Purpose

🐍 Python	Application development

🖼️ Tkinter	Desktop GUI

🖱️ TkinterDnD2	Drag-and-drop support

🗜️ Zstandard	Compression engine

🔐 SHA-256	Integrity verification

📦 PyInstaller	Windows application packaging

🔧 PowerShell	Windows development workflow

📋 Requirements

Runtime Dependencies

zstandard==0.25.0

tkinterdnd2==0.6.3

Build Dependencies

pyinstaller==6.22.3

🚀 Installation



Clone the repository:



git clone https://github.com/karnalking09/NOVA-COMPRESSOR.git

cd NOVA-COMPRESSOR



Create a virtual environment:



python -m venv .venv



Activate it:



.\\.venv\\Scripts\\Activate.ps1



Install runtime dependencies:



python -m pip install -r requirements.txt

▶️ Run From Source

python app.py

🏗️ Build Windows Application



Install build dependencies:



python -m pip install -r requirements-build.txt



Build:



python -m PyInstaller --windowed --name "NOVA COMPRESSOR" app.py



Generated application:



dist/

└── NOVA COMPRESSOR/

&#x20;   └── NOVA COMPRESSOR.exe

🧪 Development Verification



Syntax check:



python -m py\_compile app.py



Whitespace check:



git diff --check



Repository status:



git status

📁 Project Structure

NOVA-COMPRESSOR/

│

├── app.py

├── compressor\_core.py

├── NOVA COMPRESSOR.spec

├── VERSION

├── requirements.txt

├── requirements-build.txt

├── README.md

└── .gitignore

🧱 Architecture

&#x20;                ┌─────────────────────┐

&#x20;                │      NOVA GUI       │

&#x20;                │       app.py        │

&#x20;                └──────────┬──────────┘

&#x20;                           │

&#x20;                           ▼

&#x20;                ┌─────────────────────┐

&#x20;                │ Compression Engine  │

&#x20;                │ compressor\_core.py  │

&#x20;                └──────────┬──────────┘

&#x20;                           │

&#x20;            ┌──────────────┼──────────────┐

&#x20;            ▼              ▼              ▼

&#x20;       Zstandard        SHA-256       File/Folder

&#x20;       Compression      Integrity      Handling

&#x20;            │              │              │

&#x20;            └──────────────┼──────────────┘

&#x20;                           ▼

&#x20;                ┌─────────────────────┐

&#x20;                │ Output / Validation │

&#x20;                └─────────────────────┘

🗺️ Roadmap

&#x20;Expanded automated test coverage

&#x20;Additional archive workflows

&#x20;Further performance optimization

&#x20;Improved release automation

&#x20;Additional Windows packaging improvements

&#x20;Extended compression diagnostics

🔒 Security



Please do not publish sensitive information such as:



API keys

Passwords

Access tokens

Private credentials

Personal secrets



Security-related reporting should follow the project's SECURITY.md policy once it is added.



🤝 Contributing



Contributions are welcome.



Before submitting a change:



Keep changes focused.

Test affected functionality.

Run syntax and validation checks.

Avoid committing generated files.

Update documentation when behavior changes.

Provide a clear commit message.

📄 License



License information will be added to the repository in a dedicated LICENSE file.



👤 Author



Dev Kumar



GitHub: @karnalking09



⭐ Support the Project



If you find NOVA COMPRESSOR useful:



⭐ Star the repository

🐛 Report reproducible bugs

💡 Suggest improvements

🔧 Contribute improvements

<div align="center">

NOVA COMPRESSOR



Compress • Verify • Manage



Made with Python and Zstandard.

