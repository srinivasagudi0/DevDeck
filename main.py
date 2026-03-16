from collections import Counter
from datetime import datetime, timedelta, timezone

import requests
import streamlit as st


API_URL = "https://api.github.com"
TIMEOUT = 20
REPO_LIMIT = 100
EVENT_LIMIT = 30


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
        raise ValueError(f"GitHub API error: {message}")

    return response.json()


@st.cache_data(show_spinner=False, ttl=300)
def get_token_user(token):
    if not token:
        return None
    try:
        return get_data("/user", token)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=300)
def load_user_data(username, token=""):
    token_user = get_token_user(token)
    use_my_profile = token_user and token_user.get("login", "").lower() == username.lower()

    if use_my_profile:
        user = get_data("/user", token)
        repos = get_data(
            "/user/repos",
            token,
            params={"sort": "updated", "per_page": REPO_LIMIT, "affiliation": "owner"},
        )
        events = get_data(
            f"/users/{username}/events",
            token,
            params={"per_page": EVENT_LIMIT},
        )
    else:
        user = get_data(f"/users/{username}", token)
        repos = get_data(
            f"/users/{username}/repos",
            token,
            params={"sort": "updated", "per_page": REPO_LIMIT},
        )
        events = get_data(
            f"/users/{username}/events/public",
            token,
            params={"per_page": EVENT_LIMIT},
        )

    return user, repos, events, bool(use_my_profile)


@st.cache_data(show_spinner=False, ttl=300)
def load_repo_data(owner, repo_name, token=""):
    repo = get_data(f"/repos/{owner}/{repo_name}", token)
    pulls = get_data(
        f"/repos/{owner}/{repo_name}/pulls",
        token,
        params={"state": "open", "per_page": 10},
    )
    issues = get_data(
        f"/repos/{owner}/{repo_name}/issues",
        token,
        params={"state": "open", "per_page": 20},
    )
    commits = get_data(
        f"/repos/{owner}/{repo_name}/commits",
        token,
        params={"per_page": 10},
    )
    languages = get_data(f"/repos/{owner}/{repo_name}/languages", token)

    readme_url = ""
    try:
        readme = get_data(f"/repos/{owner}/{repo_name}/readme", token)
        readme_url = readme.get("html_url", "")
    except ValueError:
        readme_url = ""

    open_issues = []
    for issue in issues:
        if "pull_request" not in issue:
            open_issues.append(issue)

    return repo, pulls, open_issues, commits, languages, readme_url


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def turn_time_into_text(value):
    time_value = parse_time(value)
    if not time_value:
        return "Unknown"

    now = datetime.now(timezone.utc)
    gap = now - time_value.astimezone(timezone.utc)

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
    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if number >= 1_000:
        return f"{number / 1_000:.1f}K"
    return str(number)


def repo_summary(repo, languages):
    if repo.get("description"):
        return repo["description"]

    topics = repo.get("topics") or []
    language_names = list(languages.keys())[:3]
    if language_names:
        tools_text = ", ".join(language_names)
    else:
        tools_text = repo.get("language") or "mixed tools"

    if topics:
        return f"{repo['name']} focuses on {', '.join(topics[:3])} and uses {tools_text}."

    return f"{repo['name']} is an active repository built with {tools_text}."


def get_recent_activity(events):
    items = []
    for event in events[:10]:
        repo_name = event.get("repo", {}).get("name", "Unknown repo")
        event_type = event.get("type", "")
        payload = event.get("payload", {})

        if event_type == "PushEvent":
            count = len(payload.get("commits", []))
            text = f"Pushed {count} commit{'s' if count != 1 else ''} to {repo_name}"
        elif event_type == "IssuesEvent":
            action = payload.get("action", "updated").title()
            number = payload.get("issue", {}).get("number", "")
            text = f"{action} issue #{number} in {repo_name}"
        elif event_type == "PullRequestEvent":
            action = payload.get("action", "updated").title()
            title = payload.get("pull_request", {}).get("title", "Untitled")
            text = f"{action} PR '{title}' in {repo_name}"
        elif event_type == "CreateEvent":
            ref_type = payload.get("ref_type", "item")
            text = f"Created new {ref_type} in {repo_name}"
        elif event_type == "WatchEvent":
            text = f"Starred {repo_name}"
        else:
            text = f"{event_type.replace('Event', '')} activity in {repo_name}"

        items.append(
            {
                "time": turn_time_into_text(event.get("created_at")),
                "text": text,
            }
        )
    return items


def activity_sections(events):
    grouped = {"Today": [], "Yesterday": [], "Earlier": []}

    for item in get_recent_activity(events):
        time_text = item["time"]
        if time_text in {"just now", "yesterday"} or "min ago" in time_text or "hours ago" in time_text:
            if time_text == "yesterday":
                grouped["Yesterday"].append(item)
            else:
                grouped["Today"].append(item)
        else:
            grouped["Earlier"].append(item)

    return grouped


def get_selected_repo_events(events, full_name):
    repo_events = []
    for event in events:
        if event.get("repo", {}).get("name") == full_name:
            repo_events.append(event)
    return repo_events


def commit_streak(events):
    push_days = set()

    for event in events:
        if event.get("type") != "PushEvent":
            continue
        event_time = parse_time(event.get("created_at"))
        if event_time:
            push_days.add(event_time.date())

    if not push_days:
        return 0

    sorted_days = sorted(push_days, reverse=True)
    streak = 1

    for index in range(len(sorted_days) - 1):
        if sorted_days[index] - sorted_days[index + 1] == timedelta(days=1):
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


def tracked_commit_count(events):
    total = 0
    for event in events:
        if event.get("type") == "PushEvent":
            total += len(event.get("payload", {}).get("commits", []))
    return total


def get_repo_task_list(repo, pulls, issues, readme_url):
    tasks = []

    if not repo.get("description"):
        tasks.append("Add a repository description.")
    if not repo.get("homepage"):
        tasks.append("Add a demo link or homepage.")
    if not repo.get("license"):
        tasks.append("Add a license file.")
    if issues:
        tasks.append(f"Triage {len(issues)} open issue(s).")
    if pulls:
        tasks.append(f"Review {len(pulls)} open pull request(s).")
    if not readme_url:
        tasks.append("Add a README file.")

    if not tasks:
        tasks.append("Everything looks solid. Keep the project updated.")

    return tasks[:6]


def card_html(title, body, icon=""):
    icon_text = f"<span class='card-icon'>{icon}</span>" if icon else ""
    return f"""
    <div class="stat-card">
        <div class="stat-title">{icon_text}{title}</div>
        <div class="stat-body">{body}</div>
    </div>
    """


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
            padding-top: 1.2rem;
            padding-bottom: 2rem;
            max-width: 1450px;
        }
        h1, h2, h3, p, label, div {
            color: #eef2ff;
        }
        .panel, .stat-card, .hero {
            background: linear-gradient(180deg, rgba(36, 44, 61, 0.96), rgba(24, 31, 45, 0.94));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 18px;
            box-shadow: 0 18px 40px rgba(0, 0, 0, 0.28);
        }
        .hero {
            padding: 1.1rem 1.3rem;
            margin-bottom: 1rem;
        }
        .hero-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
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
        .top-nav {
            display: flex;
            gap: 1.25rem;
            align-items: center;
            color: #c6d3ef;
            font-weight: 700;
            font-size: 0.95rem;
        }
        .top-nav .active {
            color: #ffffff;
            border-bottom: 2px solid #7c9cff;
            padding-bottom: 0.2rem;
        }
        .panel {
            padding: 1.05rem;
            min-height: 100%;
        }
        .panel-title {
            font-size: 1.1rem;
            font-weight: 700;
            margin-bottom: 0.9rem;
        }
        .repo-button button {
            text-align: left;
            justify-content: flex-start;
            min-height: 64px;
            border-radius: 14px;
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.06);
            color: #eef2ff;
            font-weight: 700;
            white-space: normal;
        }
        .repo-selected button {
            background: linear-gradient(90deg, rgba(100, 133, 255, 0.20), rgba(255, 255, 255, 0.06));
            border-color: rgba(120, 153, 255, 0.55);
        }
        .action-button button {
            width: 100%;
            border-radius: 12px;
            background: #1f2d44;
            border: 1px solid rgba(138, 160, 197, 0.35);
            color: #eef2ff;
            font-weight: 700;
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
        .small-text {
            color: #a9b4ce;
            font-size: 0.88rem;
        }
        .overview-metrics {
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 0.8rem;
            margin: 0.9rem 0 1rem 0;
        }
        .stat-card {
            padding: 1rem 1.1rem;
            min-height: 130px;
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
            font-size: 1.3rem;
            font-weight: 800;
            line-height: 1.45;
        }
        .metric-card {
            background: rgba(255, 255, 255, 0.04);
            border-radius: 16px;
            border: 1px solid rgba(255, 255, 255, 0.06);
            padding: 1rem;
        }
        .metric-label {
            color: #a4afc8;
            font-size: 0.9rem;
        }
        .metric-value {
            font-size: 1.2rem;
            font-weight: 800;
            margin-top: 0.25rem;
        }
        .section-title {
            text-align: center;
            font-size: 1rem;
            font-weight: 800;
            margin: 1.3rem 0 0.9rem 0;
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
        .copy-box {
            background: rgba(17, 23, 34, 0.85);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 0.85rem 1rem;
            font-family: monospace;
            color: #e9f0ff;
            margin-top: 0.5rem;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 1rem;
        }
        .stTabs [data-baseweb="tab"] {
            color: #c7d1e8;
            font-weight: 700;
        }
        .stTabs [aria-selected="true"] {
            color: #ffffff;
        }
        .stTextInput input, .stNumberInput input {
            background: rgba(18, 24, 36, 0.92);
            color: #eff4ff;
        }
        @media (max-width: 900px) {
            .hero-top {
                flex-direction: column;
                align-items: flex-start;
            }
            .top-nav {
                flex-wrap: wrap;
                gap: 0.8rem;
            }
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


def keep_repo_selection(repo_names):
    current = st.session_state.get("selected_repo_name")
    if current not in repo_names:
        st.session_state["selected_repo_name"] = repo_names[0]


def show_repo_sidebar_list(repos):
    for index, repo in enumerate(repos):
        label = f"{repo['name']}\n{repo.get('language') or 'No language'} • {turn_time_into_text(repo.get('updated_at'))}"
        container_class = "repo-button repo-selected" if repo["name"] == st.session_state["selected_repo_name"] else "repo-button"
        with st.container():
            st.markdown(f"<div class='{container_class}'>", unsafe_allow_html=True)
            if st.button(label, key=f"repo_pick_{index}", use_container_width=True):
                st.session_state["selected_repo_name"] = repo["name"]
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)


def show_activity_panel(events):
    if not events:
        st.write("No recent public activity found.")
        return

    grouped = activity_sections(events)
    for section_name, items in grouped.items():
        if not items:
            continue
        st.markdown(f"##### {section_name}")
        for item in items:
            st.markdown(
                f"""
                <div class="feed-row">
                    <div class="feed-time">{item['time']}</div>
                    <div class="feed-summary">{item['text']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def show_repo_metrics(repo, issues, pulls, languages):
    total_language_bytes = sum(languages.values())
    top_language = repo.get("language") or (list(languages.keys())[0] if languages else "Unknown")
    metrics = [
        ("Stars", str(repo["stargazers_count"])),
        ("Forks", str(repo["forks_count"])),
        ("Size", f"{repo['size'] / 1024:.1f} MB"),
        ("Last Commit", turn_time_into_text(repo.get("pushed_at"))),
        ("Open Issues", str(len(issues))),
        ("Open PRs", str(len(pulls))),
        ("Main Language", top_language),
        ("Language Bytes", short_number(total_language_bytes) if total_language_bytes else "N/A"),
    ]

    st.markdown("<div class='overview-metrics'>", unsafe_allow_html=True)
    for label, value in metrics:
        st.markdown(
            f"""
            <div class="metric-card">
                <div class="metric-label">{label}</div>
                <div class="metric-value">{value}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def show_quick_actions(repo):
    st.markdown("#### Quick Actions")
    col1, col2, col3 = st.columns(3)
    col1.link_button("Open Repo", repo["html_url"], use_container_width=True)
    col2.link_button("Create Issue", f"{repo['html_url']}/issues/new", use_container_width=True)
    col3.link_button("Open Pull Requests", f"{repo['html_url']}/pulls", use_container_width=True)

    with st.expander("Local Commands", expanded=True):
        clone_command = f"git clone {repo['clone_url']}"
        vscode_command = f"code {repo['name']}"
        st.caption("These are local helper commands. Copy and run them in your terminal.")
        st.markdown(f"<div class='copy-box'>{clone_command}</div>", unsafe_allow_html=True)
        st.code(clone_command, language="bash")
        st.markdown(f"<div class='copy-box'>{vscode_command}</div>", unsafe_allow_html=True)
        st.code(vscode_command, language="bash")


def show_commit_feed(commits):
    if not commits:
        st.write("No commits found for this repository.")
        return

    for commit in commits[:5]:
        message = commit["commit"]["message"].splitlines()[0]
        author = commit["commit"].get("author", {}).get("name", "Unknown author")
        time_text = turn_time_into_text(commit["commit"].get("author", {}).get("date"))
        st.markdown(
            f"""
            <div class="list-row">
                <div style="font-size:1.05rem;">✔</div>
                <div style="flex:1;">
                    <div class="feed-summary">{message}</div>
                    <div class="small-text">{author} • {time_text}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_overview(user, repos, events, repo, pulls, issues, commits, languages, readme_url, using_token_profile):
    left, right = st.columns([1.05, 2.15], gap="large")

    with left:
        st.markdown("<div class='panel'><div class='panel-title'>My Repositories</div>", unsafe_allow_html=True)
        show_repo_sidebar_list(repos)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown("<div class='panel'><div class='panel-title'>Recent Activity</div>", unsafe_allow_html=True)
        show_activity_panel(events)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)

        st.markdown("<div class='panel'><div class='panel-title'>Repository Overview</div>", unsafe_allow_html=True)
        show_repo_metrics(repo, issues, pulls, languages)
        st.markdown("#### AI Summary")
        st.write(repo_summary(repo, languages))

        if repo.get("topics"):
            for topic in repo["topics"][:6]:
                st.markdown(f"<span class='pill'>{topic}</span>", unsafe_allow_html=True)

        show_quick_actions(repo)

        if readme_url:
            st.link_button("Open README", readme_url, use_container_width=True)

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='section-title'>Stats & Insights</div>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3, gap="large")

    repo_events = get_selected_repo_events(events, repo["full_name"])
    profile_mode_text = "Authenticated profile" if using_token_profile else "Public profile"

    with col1:
        st.markdown(card_html("Coding Streak", f"{commit_streak(events)} day streak", "🔥"), unsafe_allow_html=True)

    with col2:
        body = (
            f"Tracked commits: {tracked_commit_count(events)}<br>"
            f"Active repos: {len(repos)}<br>"
            f"Languages: {language_list(repos)}<br>"
            f"Mode: {profile_mode_text}"
        )
        st.markdown(card_html("Developer Stats", body, "📁"), unsafe_allow_html=True)

    with col3:
        body = (
            f"Projects shipped: {st.session_state['ship_projects']}<br>"
            f"Hours coded: {st.session_state['ship_hours']}<br>"
            f"Cookies earned: {st.session_state['ship_cookies']}<br>"
            f"Repo events shown: {len(repo_events)}"
        )
        st.markdown(card_html("Hack Club Ship Log", body, "🚢"), unsafe_allow_html=True)

    bottom_left, bottom_right = st.columns(2, gap="large")
    with bottom_left:
        st.markdown("<div class='panel'><div class='panel-title'>Recent Commits Feed</div>", unsafe_allow_html=True)
        show_commit_feed(commits)
        st.markdown("</div>", unsafe_allow_html=True)

    with bottom_right:
        st.markdown("<div class='panel'><div class='panel-title'>Repository Details</div>", unsafe_allow_html=True)
        details = [
            ("Visibility", "Private" if repo.get("private") else "Public"),
            ("Default Branch", repo.get("default_branch", "Unknown")),
            ("Watchers", str(repo.get("watchers_count", 0))),
            ("Subscribers", str(repo.get("subscribers_count", 0))),
            ("License", repo.get("license", {}).get("name", "No license")),
            ("Homepage", repo.get("homepage") or "No homepage"),
        ]
        for label, value in details:
            st.markdown(
                f"""
                <div class="list-row">
                    <div style="flex:1;">
                        <div class="feed-summary">{label}</div>
                        <div class="small-text">{value}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("</div>", unsafe_allow_html=True)


def show_pull_requests(repo, pulls):
    st.markdown("<div class='panel'><div class='panel-title'>Open Pull Requests</div>", unsafe_allow_html=True)
    st.link_button("Open Pull Requests on GitHub", f"{repo['html_url']}/pulls", use_container_width=True)

    if not pulls:
        st.write("No open pull requests for this repository.")
    else:
        for pr in pulls:
            st.markdown(
                f"""
                <div class="list-row">
                    <div style="flex:1;">
                        <div class="feed-summary">{pr['title']}</div>
                        <div class="small-text">#{pr['number']} by {pr['user']['login']} • {turn_time_into_text(pr['created_at'])}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button(f"Open PR #{pr['number']}", pr["html_url"], use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


def show_issues(repo, issues):
    st.markdown("<div class='panel'><div class='panel-title'>Open Issues</div>", unsafe_allow_html=True)
    st.link_button("Open Issues on GitHub", f"{repo['html_url']}/issues", use_container_width=True)

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
                        <div class="small-text">#{issue['number']} • {label_text} • {turn_time_into_text(issue['created_at'])}</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.link_button(f"Open Issue #{issue['number']}", issue["html_url"], use_container_width=True)

    st.markdown("</div>", unsafe_allow_html=True)


def show_tasks(repo, pulls, issues, commits, readme_url):
    st.markdown("<div class='panel'><div class='panel-title'>Suggested Tasks</div>", unsafe_allow_html=True)

    for task in get_repo_task_list(repo, pulls, issues, readme_url):
        st.markdown(
            f"""
            <div class="list-row">
                <div style="font-size:1.15rem;">☐</div>
                <div class="feed-summary">{task}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("#### Latest Commits")
    show_commit_feed(commits[:3])

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
        <div class="hero">
            <div class="hero-top">
                <div>
                    <div class="brand">DevDeck</div>
                    <div class="subtle">Your GitHub command center for repositories, commits, pull requests, issues, and project stats.</div>
                </div>
                <div class="top-nav">
                    <span class="active">Overview</span>
                    <span>Pull Requests</span>
                    <span>Issues</span>
                    <span>Tasks</span>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.sidebar:
        st.header("Connection")
        username = st.text_input("GitHub Username", value=st.session_state.get("username", ""))
        token = st.text_input("GitHub Token", type="password", help="Optional. Adds higher rate limits and can unlock your own private profile data.")

        st.header("Ship Log")
        st.session_state["ship_projects"] = st.number_input("Projects shipped", min_value=0, step=1, value=st.session_state["ship_projects"])
        st.session_state["ship_hours"] = st.number_input("Hours coded", min_value=0, step=1, value=st.session_state["ship_hours"])
        st.session_state["ship_cookies"] = st.number_input("Cookies earned", min_value=0, step=1, value=st.session_state["ship_cookies"])

    if not username.strip():
        st.info("Enter a GitHub username in the sidebar to load DevDeck.")
        return

    username = username.strip()
    token = token.strip()
    st.session_state["username"] = username

    try:
        user, repos, events, using_token_profile = load_user_data(username, token)
    except ValueError as error:
        st.error(str(error))
        return
    except requests.RequestException as error:
        st.error(f"Network error: {error}")
        return

    if not repos:
        st.warning("This user has no repositories to display.")
        return

    repo_names = [repo["name"] for repo in repos]
    keep_repo_selection(repo_names)

    top_left, top_right = st.columns([2.2, 1.1])
    with top_left:
        selected_name = st.selectbox("Selected Repository", repo_names, index=repo_names.index(st.session_state["selected_repo_name"]))
        if selected_name != st.session_state["selected_repo_name"]:
            st.session_state["selected_repo_name"] = selected_name
            st.rerun()
    with top_right:
        st.markdown("<div style='height: 1.9rem;'></div>", unsafe_allow_html=True)
        st.write(
            f"Viewing **{user.get('name') or user['login']}** • {user['public_repos']} public repos • {short_number(user['followers'])} followers"
        )

    selected_repo = None
    for repo in repos:
        if repo["name"] == st.session_state["selected_repo_name"]:
            selected_repo = repo
            break

    try:
        repo, pulls, issues, commits, languages, readme_url = load_repo_data(
            selected_repo["owner"]["login"],
            selected_repo["name"],
            token,
        )
    except ValueError as error:
        st.error(str(error))
        return
    except requests.RequestException as error:
        st.error(f"Network error: {error}")
        return

    tab1, tab2, tab3, tab4 = st.tabs(["Overview", "Pull Requests", "Issues", "Tasks"])

    with tab1:
        show_overview(user, repos, events, repo, pulls, issues, commits, languages, readme_url, using_token_profile)
    with tab2:
        show_pull_requests(repo, pulls)
    with tab3:
        show_issues(repo, issues)
    with tab4:
        show_tasks(repo, pulls, issues, commits, readme_url)


if __name__ == "__main__":
    run()
