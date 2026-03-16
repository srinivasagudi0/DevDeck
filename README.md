# DevDeck

DevDeck is a Streamlit dashboard for viewing GitHub repositories, recent activity, pull requests, issues, commit highlights, and simple developer stats in one place.

## Features

- Select and switch between repositories from the dashboard
- View recent GitHub activity in a timeline
- See repository insights like stars, forks, size, issues, pull requests, and languages
- Check recent commits for the selected repository
- Use quick links for repo, issue, and pull request pages
- Copy local helper commands for cloning and opening a repo in VS Code
- Track a coding streak, recent commit activity, and manual ship log stats

## Tech Stack

- Python
- Streamlit
- GitHub REST API
- Requests

## Requirements

- Python 3.10+

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run

Start the app with either command:

```bash
streamlit run app.py
```

```bash
streamlit run main.py
```

## How To Use

1. Enter a GitHub username in the sidebar.
2. Optionally enter a GitHub token for better rate limits and access to your own authenticated profile data.
3. Pick a repository from the selector or the repository list.
4. Use the tabs to view overview, pull requests, issues, and tasks.

## Inputs

- `GitHub Username`: required
- `GitHub Token`: optional
- `Projects shipped`: manual ship log value
- `Hours coded`: manual ship log value
- `Cookies earned`: manual ship log value

## Project Files

- [main.py](/Users/srinivasagudi/Desktop/DevDock/main.py): main Streamlit app
- [app.py](/Users/srinivasagudi/Desktop/DevDock/app.py): small launcher file
- [requirements.txt](/Users/srinivasagudi/Desktop/DevDock/requirements.txt): project dependencies
- [Plan.txt](/Users/srinivasagudi/Desktop/DevDock/Plan.txt): original product plan

## Notes

- Public GitHub profiles work without a token.
- Some local-machine actions cannot be run directly by Streamlit, so DevDeck shows them as copyable commands instead.
- Private repository access depends on the token you provide.
