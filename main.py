from collections import Counter
from datetime import datetime, timedelta

import requests
import streamlit as st


API_URL = "https://api.github.com"
TIMEOUT = 15


def get_headers(token=""):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DevDeck",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def get_data(path, token="", params=None):
    response = requests.get(
        f"{API_URL}{path}",
        headers=get_headers(token),
        params=params,
        timeout=TIMEOUT,
    )

    if response.status_code == 404:
        raise ValueError("GitHub user or repository was not found.")

    if response.status_code == 403 and "rate limit" in response.text.lower():
        raise ValueError("GitHub API rate limit reached. Add a token in the sidebar and try again.")

    if not response.ok:
        try:
            message = response.json().get("message", response.text)
        except ValueError:
            message = response.text
        raise ValueError(message)

    return response.json()


@st.cache_data(show_spinner=False, ttl=300)
def load_user_data(username, token=""):
    user = get_data(f"/users/{username}", token)
    repos = get_data(
        f"/users/{username}/repos",
        token,
        params={"sort": "updated", "per_page": 100},
    )
    events = get_data(
        f"/users/{username}/events/public",
        token,
        params={"per_page": 30},
    )
    return user, repos, events


@st.cache_data(show_spinner=False, ttl=300)
def load_repo_data(owner, repo_name, token=""):
    pulls = get_data(
        f"/repos/{owner}/{repo_name}/pulls",
        token,
        params={"state": "open", "per_page": 10},
    )
    issues = get_data(
        f"/repos/{owner}/{repo_name}/issues",
        token,
        params={"state": "open", "per_page": 10},
    )
    commits = get_data(
        f"/repos/{owner}/{repo_name}/commits",
        token,
        params={"per_page": 5},
    )
    languages = get_data(f"/repos/{owner}/{repo_name}/languages", token)

    readme_url = ""
    try:
        readme = get_data(f"/repos/{owner}/{repo_name}/readme", token)
        readme_url = readme.get("download_url", "")
    except ValueError:
        readme_url = ""

    open_issues = []
    for issue in issues:
        if "pull_request" not in issue:
            open_issues.append(issue)

    return pulls, open_issues, commits, languages, readme_url


def turn_time_into_text(value):
    if not value:
        return "Unknown"

    try:
        time_value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return "Unknown"

    now = datetime.now(time_value.tzinfo)
    gap = now - time_value

    if gap < timedelta(minutes=1):
        return "just now"
    if gap < timedelta(hours=1):
        return f"{int(gap.total_seconds() // 60)} min ago"
    if gap < timedelta(days=1):
        return f"{int(gap.total_seconds() // 3600)} hours ago"
    if gap < timedelta(days=2):
        return "yesterday"
    return f"{gap.days} days ago"


def short_number(number):
    if number >= 1000000:
        return f"{number / 1000000:.1f}M"
    if number >= 1000:
        return f"{number / 1000:.1f}K"
    return str(number)


def repo_summary(repo, languages):
    if repo.get("description"):
        return repo["description"]

    topic_list = repo.get("topics") or []
    if languages:
        top_languages = ", ".join(list(languages.keys())[:3])
    else:
        top_languages = repo.get("language") or "mixed tools"

    if topic_list:
        return f"{repo['name']} focuses on {', '.join(topic_list[:3])} and uses {top_languages}."

    return f"{repo['name']} is an active repository built with {top_languages}."


def recent_activity(events):
    activity = []

    for event in events[:8]:
        repo_name = event.get("repo", {}).get("name", "Unknown repo")
        event_type = event.get("type", "")
        payload = event.get("payload", {})

        if event_type == "PushEvent":
            count = len(payload.get("commits", []))
            message = f"Pushed {count} commit{'s' if count != 1 else ''} to {repo_name}"
        elif event_type == "IssuesEvent":
            action = payload.get("action", "updated").title()
            number = payload.get("issue", {}).get("number", "")
            message = f"{action} issue #{number} in {repo_name}"
        elif event_type == "PullRequestEvent":
            action = payload.get("action", "updated").title()
            title = payload.get("pull_request", {}).get("title", "Untitled")
            message = f"{action} PR '{title}' in {repo_name}"
        elif event_type == "CreateEvent":
            item_type = payload.get("ref_type", "item")
            message = f"Created new {item_type} in {repo_name}"
        elif event_type == "WatchEvent":
            message = f"Starred {repo_name}"
        else:
            message = f"{event_type.replace('Event', '')} activity in {repo_name}"

        activity.append(
            {
                "time": turn_time_into_text(event.get("created_at")),
                "message": message,
            }
        )

    return activity


def commit_streak(events):
    push_days = []

    for event in events:
        if event.get("type") != "PushEvent":
            continue

        created_at = event.get("created_at")
        if not created_at:
            continue

        try:
            day = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
        except ValueError:
            continue

        if day not in push_days:
            push_days.append(day)

    push_days.sort(reverse=True)

    if not push_days:
        return 0

    streak = 1
    for i in range(len(push_days) - 1):
        if push_days[i] - push_days[i + 1] == timedelta(days=1):
            streak += 1
        else:
            break

    return streak


def language_list(repos):
    counts = Counter()
    for repo in repos:
        if repo.get("language"):
            counts[repo["language"]] += 1

    if not counts:
        return "No language data"

    common = counts.most_common(4)
    return ", ".join(name for name, _ in common)


def recent_commit_count(events):
    total = 0
    for event in events:
        if event.get("type") == "PushEvent":
            total += len(event.get("payload", {}).get("commits", []))
    return total


def task_list(repo, pulls, readme_url):
    tasks = []

    if not repo.get("description"):
        tasks.append("Add a repository description.")
    if not repo.get("homepage"):
        tasks.append("Add a demo link or homepage.")
    if not repo.get("license"):
        tasks.append("Add a license file.")
    if repo.get("open_issues_count", 0) > 0:
        tasks.append(f"Triage {repo['open_issues_count']} open issue(s).")
    if pulls:
        tasks.append(f"Review {len(pulls)} open pull request(s).")
    if not readme_url:
        tasks.append("Add a README file.")

    if not tasks:
        tasks.append("Everything looks solid. Keep the project updated.")

    return tasks[:5]


def info_card(title, body, icon=""):
    icon_html = f"<span class='card-icon'>{icon}</span>" if icon else ""
    st.markdown(
        f"""
        <div class="stat-card">
            <div class="stat-title">{icon_html}{title}</div>
            <div class="stat-body">{body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def add_styles():
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(87, 116, 255, 0.12), transparent 28%),
                radial-gradient(circle at bottom right, rgba(53, 198, 173, 0.10), transparent 24%),
                linear-gradient(180deg, #111725 0%, #0d1320 100%);
            color: #eef2ff;
        }
        .block-container {
            padding-top: 1.5rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }
        .panel, .stat-card {
            background: linear-gradient(180deg, rgba(36, 44, 61, 0.95), rgba(28, 35, 50, 0.92));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28);
        }
        .panel {
            padding: 1.1rem;
            min-height: 100%;
        }
        .panel-title {
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 1rem;
        }
        .app-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0.9rem 1.2rem;
            margin-bottom: 1rem;
        }
        .brand {
            font-size: 2rem;
            font-weight: 800;
            letter-spacing: -0.03em;
        }
        .subtle {
            color: #9aa6c2;
            font-size: 0.95rem;
        }
        .repo-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 0.8rem;
            padding: 0.85rem 0.95rem;
            margin-bottom: 0.6rem;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.05);
        }
        .repo-item.selected {
            background: linear-gradient(90deg, rgba(100, 133, 255, 0.20), rgba(255, 255, 255, 0.06));
            border-color: rgba(120, 153, 255, 0.55);
        }
        .repo-name {
            font-size: 1.02rem;
            font-weight: 700;
        }
        .repo-meta {
            color: #a9b4ce;
            font-size: 0.85rem;
            margin-top: 0.15rem;
        }
        .feed-row, .list-row {
            display: flex;
            align-items: center;
            gap: 0.8rem;
            padding: 0.8rem 0;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
        }
        .feed-row:last-child, .list-row:last-child {
            border-bottom: none;
        }
        .feed-time {
            color: #a4afc8;
            min-width: 120px;
            font-size: 0.95rem;
        }
        .feed-summary {
            font-size: 1rem;
            font-weight: 600;
        }
        .overview-metrics {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.8rem;
            margin: 0.95rem 0 1.15rem 0;
        }
        .stat-card {
            padding: 1rem 1.1rem;
            min-height: 140px;
        }
        .stat-title {
            color: #f4f6fb;
            font-size: 1rem;
            font-weight: 700;
            margin-bottom: 0.8rem;
        }
        .card-icon {
            margin-right: 0.45rem;
        }
        .stat-body {
            color: #dce3f6;
            font-size: 1.35rem;
            font-weight: 800;
            line-height: 1.5;
        }
        .metric-label {
            color: #a4afc8;
            font-size: 0.92rem;
        }
        .metric-value {
            font-size: 1.25rem;
            font-weight: 800;
        }
        .section-title {
            text-align: center;
            font-size: 1rem;
            font-weight: 800;
            margin: 1.4rem 0 0.9rem 0;
            color: #f4f6fb;
        }
        .pill {
            display: inline-block;
            padding: 0.28rem 0.6rem;
            border-radius: 999px;
            background: rgba(102, 173, 255, 0.16);
            color: #dce7ff;
            font-size: 0.82rem;
            margin-right: 0.4rem;
            margin-bottom: 0.4rem;
        }
        .stButton > button {
            width: 100%;
            border-radius: 12px;
            background: #1f2d44;
            border: 1px solid rgba(138, 160, 197, 0.35);
            color: #eef2ff;
            font-weight: 600;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
            color: #c7d1e8;
            font-weight: 700;
        }
        .stTextInput input {
            background: rgba(18, 24, 36, 0.92);
            color: #eff4ff;
        }
        @media (max-width: 900px) {
            .overview-metrics {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .feed-row {
                align-items: flex-start;
                flex-direction: column;
            }
            .feed-time {
                min-width: unset;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def show_repo_list(repos, selected_name):
    for repo in repos[:8]:
        selected_class = "selected" if repo["name"] == selected_name else ""
        st.markdown(
            f"""
            <div class="repo-item {selected_class}">
                <div>
                    <div class="repo-name">{repo['name']}</div>
                    <div class="repo-meta">{repo.get('language') or 'No language'} • Updated {turn_time_into_text(repo.get('updated_at'))}</div>
                </div>
                <div style="font-size:1.2rem;color:#a6b7df;">›</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_overview(user, repos, events, repo, pulls, commits, languages, readme_url):
    left, right = st.columns([1.1, 2.2], gap="large")

    with left:
        st.markdown("<div class='panel'><div class='panel-title'>My Repositories</div>", unsafe_allow_html=True)
        show_repo_list(repos, repo["name"])

        button_1, button_2 = st.columns(2)
        button_1.link_button("Open Repo", repo.get("html_url", "#"), use_container_width=True)
        button_2.link_button("Create Issue", f"{repo.get('html_url', '#')}/issues/new", use_container_width=True)

        st.code(f"git clone {repo.get('clone_url', '')}", language="bash")
        st.code(f"code {repo['name']}", language="bash")
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='panel'><div class='panel-title'>Recent Activity</div>", unsafe_allow_html=True)
        for item in recent_activity(events):
            st.markdown(
                f"""
                <div class="feed-row">
                    <div class="feed-time">{item['time']}</div>
                    <div class="feed-summary">{item['message']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        st.markdown("<div class='panel'><div class='panel-title'>Repository Overview</div>", unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="overview-metrics">
                <div class="stat-card">
                    <div class="metric-label">Stars</div>
                    <div class="metric-value">{repo['stargazers_count']}</div>
                </div>
                <div class="stat-card">
                    <div class="metric-label">Forks</div>
                    <div class="metric-value">{repo['forks_count']}</div>
                </div>
                <div class="stat-card">
                    <div class="metric-label">Size</div>
                    <div class="metric-value">{repo['size'] / 1024:.1f} MB</div>
                </div>
                <div class="stat-card">
                    <div class="metric-label">Last Commit</div>
                    <div class="metric-value">{turn_time_into_text(repo.get('pushed_at'))}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("#### AI Summary")
        st.write(repo_summary(repo, languages))

        for topic in repo.get("topics") or []:
            st.markdown(f"<span class='pill'>{topic}</span>", unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Stats & Insights</div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3, gap="large")

    with col1:
        info_card("Coding Streak", f"{commit_streak(events)} day streak", "🔥")

    with col2:
        info_card(
            "Developer Stats",
            (
                f"Recent commits: {recent_commit_count(events)}<br>"
                f"Repos: {len(repos)} active<br>"
                f"Languages: {language_list(repos)}"
            ),
            "📁",
        )

    with col3:
        info_card(
            "Hack Club Ship Log",
            (
                f"Projects shipped: {st.session_state['ship_projects']}<br>"
                f"Hours coded: {st.session_state['ship_hours']}<br>"
                f"Cookies earned: {st.session_state['ship_cookies']}"
            ),
            "🚢",
        )


def show_pull_requests(pulls):
    st.markdown("<div class='panel'><div class='panel-title'>Open Pull Requests</div>", unsafe_allow_html=True)

    if not pulls:
        st.write("No open pull requests for this repository.")
    else:
        for pr in pulls:
            st.markdown(
                f"""
                <div class="list-row">
                    <div style="flex:1;">
                        <div class="feed-summary">{pr['title']}</div>
                        <div class="repo-meta">#{pr['number']} by {pr['user']['login']} • {turn_time_into_text(pr['created_at'])}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button("Open PR", pr["html_url"], use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


def show_issues(issues):
    st.markdown("<div class='panel'><div class='panel-title'>Open Issues</div>", unsafe_allow_html=True)

    if not issues:
        st.write("No open issues for this repository.")
    else:
        for issue in issues:
            labels = issue.get("labels", [])
            label_text = ", ".join(label["name"] for label in labels) if labels else "No labels"

            st.markdown(
                f"""
                <div class="list-row">
                    <div style="flex:1;">
                        <div class="feed-summary">{issue['title']}</div>
                        <div class="repo-meta">#{issue['number']} • {label_text} • {turn_time_into_text(issue['created_at'])}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button("Open Issue", issue["html_url"], use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


def show_tasks(repo, pulls, commits, readme_url):
    st.markdown("<div class='panel'><div class='panel-title'>Suggested Tasks</div>", unsafe_allow_html=True)

    for task in task_list(repo, pulls, readme_url):
        st.markdown(
            f"""
            <div class="list-row">
                <div style="font-size:1.15rem;">☐</div>
                <div class="feed-summary">{task}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if commits:
        st.markdown("#### Latest Commits")
        for commit in commits[:3]:
            message = commit["commit"]["message"].splitlines()[0]
            st.write(f"• {message}")

    st.markdown("</div>", unsafe_allow_html=True)


def run():
    st.set_page_config(page_title="DevDeck", page_icon=":rocket:", layout="wide")
    add_styles()

    if "ship_projects" not in st.session_state:
        st.session_state["ship_projects"] = 0
    if "ship_hours" not in st.session_state:
        st.session_state["ship_hours"] = 0
    if "ship_cookies" not in st.session_state:
        st.session_state["ship_cookies"] = 0

    st.markdown(
        """
        <div class="panel app-header">
            <div>
                <div class="brand">DevDeck</div>
                <div class="subtle">GitHub command center for repositories, activity, and repo health.</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Connection")
        username = st.text_input("GitHub Username", value=st.session_state.get("username", ""))
        token = st.text_input("GitHub Token", type="password")

        st.header("Ship Log")
        st.session_state["ship_projects"] = st.number_input(
            "Projects shipped",
            min_value=0,
            step=1,
            value=st.session_state["ship_projects"],
        )
        st.session_state["ship_hours"] = st.number_input(
            "Hours coded",
            min_value=0,
            step=1,
            value=st.session_state["ship_hours"],
        )
        st.session_state["ship_cookies"] = st.number_input(
            "Cookies earned",
            min_value=0,
            step=1,
            value=st.session_state["ship_cookies"],
        )

    if not username:
        st.info("Enter a GitHub username in the sidebar to load DevDeck.")
        return

    st.session_state["username"] = username

    try:
        user, repos, events = load_user_data(username.strip(), token.strip())
    except ValueError as error:
        st.error(str(error))
        return
    except requests.RequestException as error:
        st.error(f"Network error: {error}")
        return

    if not repos:
        st.warning("This user has no public repositories yet.")
        return

    repo_names = [repo["name"] for repo in repos]

    top_left, top_right = st.columns([2.4, 1.1])
    with top_left:
        chosen_repo_name = st.selectbox("Selected Repository", repo_names, index=0)
    with top_right:
        st.markdown("<div style='height: 1.9rem;'></div>", unsafe_allow_html=True)
        st.write(
            f"Viewing **{user.get('name') or user['login']}** • {user['public_repos']} public repos • {short_number(user['followers'])} followers"
        )

    selected_repo = None
    for repo in repos:
        if repo["name"] == chosen_repo_name:
            selected_repo = repo
            break

    try:
        pulls, issues, commits, languages, readme_url = load_repo_data(
            selected_repo["owner"]["login"],
            selected_repo["name"],
            token.strip(),
        )
    except ValueError as error:
        st.error(str(error))
        return
    except requests.RequestException as error:
        st.error(f"Network error: {error}")
        return

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Pull Requests", "Issues", "Tasks"])

    with tab1:
        show_overview(user, repos, events, selected_repo, pulls, commits, languages, readme_url)
    with tab2:
        show_pull_requests(pulls)
    with tab3:
        show_issues(issues)
    with tab4:
        show_tasks(selected_repo, pulls, commits, readme_url)


if __name__ == "__main__":
    run()
