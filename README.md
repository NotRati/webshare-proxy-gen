# Webshare Proxy Generator Bot

A Python bot that mimics human movement to solve reCAPTCHAs and acquire proxies from Webshare. This tool supports both CLI and GUI modes for flexible operation.

## Features
- Mimics human-like browser interactions for realistic automation
- Automatically solves reCAPTCHAs
- Retrieves proxy lists from Webshare
- Supports concurrent registrations
- Headless mode for background operation
- GUI for user-friendly interaction

## Prerequisites
Before running the bot, ensure you have the following installed:
- **Python 3.8+**: Download from [python.org](https://www.python.org/downloads/)
- **Git**: For cloning the repository ([installation guide](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git))
- **uv**: A Python package manager for faster dependency installation ([uv installation](https://github.com/astral-sh/uv))
- Compatible browser (Chrome or Firefox) for Selenium automation

## Installation

### 1. Clone the Repository
Clone the project to your local machine:
```bash
git clone https://github.com/NotRati/webshare-proxy-gen
```

### 2. Navigate to the Project Directory
Move into the project folder:
```bash
cd webshare-proxy-gen
```

### 3. Install Dependencies
Install the required Python packages using `uv`:
```bash
uv pip install -r requirements.txt
```

## Running the Bot

### CLI Mode
Run the bot in standalone mode using:
```bash
uv run main.py [arguments]
```

#### Arguments for `main.py`
| Argument       | Description                                    | Default       |
|----------------|------------------------------------------------|---------------|
| `--concurrent` | Number of concurrent registrations            | 1             |
| `--headless`   | Run in headless mode (no browser UI)          | False         |
| `--total`      | Total number of registrations (-1 for infinite)| 1             |

Example:
```bash
uv run main.py --concurrent 5 --headless --total 10
```

### GUI Mode
Launch the graphical interface:
```bash
uv run gui.py
```

The GUI provides an intuitive interface to configure settings and monitor progress.


