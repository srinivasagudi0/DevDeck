# DevDeck

DevDeck is an early GitHub dashboard project intended to show a developer's repositories, activity, and repo insights in one place.

Right now, this repository contains a small Python prototype that fetches public repository data from the GitHub API. The broader product direction is captured in [Plan.txt](/Users/srinivasagudi/Desktop/DevDock/Plan.txt).

## Current Status

This project is still in a very early stage.

- `testfile.py` contains the current working prototype.
- `app.py` tries to import `run()` from `main.py`.
- `main.py` is not present in the repository right now, so `app.py` will not run as-is.

## What The Prototype Does

The current script:

- prompts for a GitHub username
- fetches that user's public repositories
- prints repository names to the terminal
- includes a partially implemented function for repository contribution stats

## Project Goal

The intended DevDeck experience is a lightweight developer dashboard with features like:

- repository listing
- recent commit activity
- repository insights such as stars, forks, and size
- quick actions for common GitHub workflows
- developer activity tracking

## Tech Direction

Planned stack from the project notes:

- Python backend
- GitHub REST API
- Streamlit for the first UI

## Requirements

- Python 3.10+
- `requests`

Install dependencies with:

```bash
pip install requests
```

## Running The Current Prototype

Run:

```bash
python testfile.py
```

You will be prompted for a GitHub username, and the script will print that user's public repositories.

## File Overview

- [testfile.py](/Users/srinivasagudi/Desktop/DevDock/testfile.py): current GitHub API prototype
- [app.py](/Users/srinivasagudi/Desktop/DevDock/app.py): app entry point stub that depends on a missing `main.py`
- [Plan.txt](/Users/srinivasagudi/Desktop/DevDock/Plan.txt): product idea, feature scope, and rough architecture notes
- [Final_Output.png](/Users/srinivasagudi/Desktop/DevDock/Final_Output.png): project asset/mockup image

## Next Steps

- add the missing `main.py` or update `app.py`
- move API logic into reusable functions
- add error handling for invalid usernames and rate limits
- build the first Streamlit interface

## Notes

This repository is currently a prototype rather than a finished application.
