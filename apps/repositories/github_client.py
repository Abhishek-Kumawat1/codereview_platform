"""
GitHub API client.
"""
import requests
from django.conf import settings


class GitHubClient:
    """
    Thin wrapper around the GitHub REST API.
    """

    BASE_URL = 'https://api.github.com'

    def __init__(self, token=None):
        self.token = token or settings.GITHUB_TOKEN
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}',
            'Accept': 'application/vnd.github+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })

    def get_pull_request_diff(self, full_name, pr_number):
        """
        Fetch the unified diff for a pull request.
        """
        url = f'{self.BASE_URL}/repos/{full_name}/pulls/{pr_number}'

        response = self.session.get(
            url,
            headers={'Accept': 'application/vnd.github.diff'},
            timeout=30,
        )

        if response.status_code == 200:
            return response.text
        return None

    def get_pull_request(self, full_name, pr_number):
        """Fetch PR metadata as JSON."""
        url = f'{self.BASE_URL}/repos/{full_name}/pulls/{pr_number}'
        response = self.session.get(url, timeout=15)
        if response.status_code == 200:
            return response.json()
        return None

    def post_commit_status(self, full_name, sha, state, description, context='CodeReview'):
        """
        Post a commit status to GitHub.
        This shows a green/red check on the PR page.

        state: 'pending', 'success', 'failure', 'error'
        """
        url = f'{self.BASE_URL}/repos/{full_name}/statuses/{sha}'
        response = self.session.post(url, json={
            'state': state,
            'description': description,
            'context': context,
        }, timeout=15)
        return response.status_code == 201