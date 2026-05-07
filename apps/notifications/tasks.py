from celery import shared_task
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.urls import reverse


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def send_comment_notification(self, comment_id):
    """
    Send email notifications when a new comment is posted.

    """

    from apps.reviews.models import Comment
    from apps.notifications.models import Notification, NotificationType

    try:
        comment = Comment.objects.select_related(
            'author',
            'review_cycle__pull_request__repository',
            'review_cycle__pull_request__author',
        ).get(pk=comment_id)
    except Comment.DoesNotExist:
        return f'Comment {comment_id} no longer exists, skipping.'

    pr = comment.review_cycle.pull_request
    cycle = comment.review_cycle


    base_url = getattr(settings, 'SITE_URL', 'http://localhost')
    action_url = f"{base_url}/reviews/{pr.pk}/"

    recipients = set()

    if pr.author and pr.author != comment.author:
        recipients.add(pr.author)

    for assignment in cycle.reviewer_assignments.select_related('reviewer').all():
        if assignment.reviewer != comment.author:
            recipients.add(assignment.reviewer)

    if not recipients:
        return 'No recipients to notify.'

    comment_author_name = (
        'AI Reviewer' if comment.is_ai_generated
        else comment.author.display_name if comment.author
        else 'Someone'
    )

    email_context = {
        'pr': pr,
        'comment_body': comment.body,
        'comment_author': comment_author_name,
        'file_path': comment.file_path,
        'line_number': comment.line_number,
        'action_url': action_url,
    }

    html_message = render_to_string(
        'notifications/email/new_comment.html',
        email_context
    )

    sent_count = 0
    for recipient in recipients:
        Notification.objects.create(
            recipient=recipient,
            notification_type=NotificationType.COMMENT_ADDED,
            title=f'New comment on PR #{pr.github_pr_number}',
            message=f'{comment_author_name}: {comment.body[:100]}',
            action_url=action_url,
        )

        send_mail(
            subject=f'[CodeReview] New comment on PR #{pr.github_pr_number}: {pr.title}',
            message=comment.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient.email],
            html_message=html_message,     
            fail_silently=False,
        )
        sent_count += 1

    return f'Notified {sent_count} recipients for comment {comment_id}'


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_review_decision_notification(self, assignment_id):
    """
    Notify the PR author when a reviewer approves or requests changes.
    """
    from apps.reviews.models import ReviewerAssignment
    from apps.notifications.models import Notification, NotificationType

    try:
        assignment = ReviewerAssignment.objects.select_related(
            'reviewer',
            'review_cycle__pull_request__author',
            'review_cycle__pull_request__repository',
        ).get(pk=assignment_id)
    except ReviewerAssignment.DoesNotExist:
        return f'Assignment {assignment_id} no longer exists, skipping.'

    pr = assignment.review_cycle.pull_request
    author = pr.author

    if not author or author == assignment.reviewer:
        return 'Author and reviewer are the same user, skipping.'

    base_url = getattr(settings, 'SITE_URL', 'http://localhost')
    action_url = f"{base_url}/reviews/{pr.pk}/"

    notif_type = (
        NotificationType.REVIEW_APPROVED
        if assignment.decision == 'approved'
        else NotificationType.CHANGES_REQUESTED
    )

    Notification.objects.create(
        recipient=author,
        notification_type=notif_type,
        title=f'PR #{pr.github_pr_number} — {assignment.get_decision_display()}',
        message=f'{assignment.reviewer.display_name} reviewed your PR.',
        action_url=action_url,
    )

    html_message = render_to_string(
        'notifications/email/review_decision.html',
        {
            'pr': pr,
            'decision': assignment.decision,
            'reviewer_name': assignment.reviewer.display_name,
            'action_url': action_url,
        }
    )

    send_mail(
        subject=f'[CodeReview] {assignment.get_decision_display()} — PR #{pr.github_pr_number}',
        message=f'{assignment.reviewer.display_name} reviewed your PR.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[author.email],
        html_message=html_message,
        fail_silently=False,
    )

    return f'Notified {author.email} of decision: {assignment.decision}'


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_reviewer_assigned_notification(self, assignment_id):
    """
    Notify a reviewer when they're assigned to a review cycle.
    """
    from apps.reviews.models import ReviewerAssignment
    from apps.notifications.models import Notification, NotificationType

    try:
        assignment = ReviewerAssignment.objects.select_related(
            'reviewer',
            'review_cycle__pull_request__author',
            'review_cycle__pull_request__repository',
        ).get(pk=assignment_id)
    except ReviewerAssignment.DoesNotExist:
        return f'Assignment {assignment_id} no longer exists, skipping.'

    pr = assignment.review_cycle.pull_request
    reviewer = assignment.reviewer

    if reviewer == pr.author:
        return 'Reviewer is the PR author, skipping.'

    base_url = getattr(settings, 'SITE_URL', 'http://localhost')
    action_url = f"{base_url}/reviews/{pr.pk}/"

    Notification.objects.create(
        recipient=reviewer,
        notification_type=NotificationType.REVIEWER_ASSIGNED,
        title=f'Review requested: PR #{pr.github_pr_number}',
        message=f'{pr.author.display_name} requested your review on "{pr.title}"',
        action_url=action_url,
    )

    html_message = render_to_string(
        'notifications/email/reviewer_assigned.html',
        {
            'pr': pr,
            'action_url': action_url,
        }
    )

    send_mail(
        subject=f'[CodeReview] Review requested — {pr.title}',
        message=f'You\'ve been asked to review PR #{pr.github_pr_number}.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[reviewer.email],
        html_message=html_message,
        fail_silently=False,
    )

    return f'Notified {reviewer.email} of assignment'

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    time_limit=120,
)
def run_ai_review(self, cycle_id):
    """
    Runs an AI pre-review on a pull request using Groq (Llama).
    Called automatically when a new ReviewCycle is created via webhook,
    or manually via the 'Run AI Review' button on the PR detail page.
    """
    import json as json_module
    from groq import Groq
    from django.conf import settings as django_settings
    from apps.reviews.models import ReviewCycle, Comment
    from apps.notifications.models import Notification, NotificationType
    from apps.repositories.github_client import GitHubClient

    try:
        cycle = ReviewCycle.objects.select_related(
            'pull_request__repository',
            'pull_request__author',
        ).get(pk=cycle_id)
    except ReviewCycle.DoesNotExist:
        return f'Cycle {cycle_id} not found.'

    pr = cycle.pull_request
    repo = pr.repository

    github = GitHubClient()
    diff = github.get_pull_request_diff(repo.full_name, pr.github_pr_number)

    if not diff:
        return f'Could not fetch diff for PR #{pr.github_pr_number}'

    MAX_DIFF_CHARS = 15000
    diff_truncated = False
    if len(diff) > MAX_DIFF_CHARS:
        diff = diff[:MAX_DIFF_CHARS]
        diff_truncated = True

    if pr.head_sha and django_settings.GITHUB_TOKEN:
        github.post_commit_status(
            repo.full_name,
            pr.head_sha,
            state='pending',
            description='AI pre-review in progress...',
            context='CodeReview / AI Pre-Review',
        )

    groq_client = Groq(api_key=django_settings.GROQ_API_KEY)

    prompt = f"""You are an expert code reviewer. You MUST respond with ONLY a JSON object matching this EXACT schema. No other text before or after the JSON.

EXACT schema:
{{
  "summary": "2-3 sentence overall assessment of the PR",
  "issues": [
    {{
      "severity": "critical",
      "file_path": "path/to/file.py",
      "line_number": 42,
      "comment": "specific actionable feedback under 100 words"
    }}
  ],
  "positive_feedback": "what the PR does well in 1-2 sentences"
}}

STRICT rules:
- severity MUST be exactly one of: critical, warning, suggestion
- file_path MUST be a string (use empty string for general comments)
- line_number MUST be an integer or null
- comment MUST be a string with actual feedback
- Maximum 6 items in issues array
- Respond with valid JSON ONLY — no markdown, no backticks, no explanation

Pull Request: {pr.title}
Description: {pr.body or 'No description provided'}
Branch: {pr.head_branch} → {pr.base_branch}
{'⚠ Note: diff was truncated to first 15,000 characters.' if diff_truncated else ''}

Diff:
{diff}"""

    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {
                    'role': 'system',
                    'content': (
                        'You are an expert code reviewer. '
                        'Always respond with valid JSON only. '
                        'Never include markdown formatting or backticks.'
                    ),
                },
                {
                    'role': 'user',
                    'content': prompt,
                }
            ],
            model='llama-3.1-8b-instant',
            temperature=0.1,
            max_tokens=1500,
        )
        response_text = chat_completion.choices[0].message.content

    except Exception as exc:
        raise self.retry(exc=exc)

    try:
        clean_response = response_text.strip()

        if clean_response.startswith('```'):
            lines = clean_response.split('\n')
            clean_response = '\n'.join(lines[1:-1]).strip()

        review_data = json_module.loads(clean_response)

        normalised_issues = []
        for issue in review_data.get('issues', []):

            if 'comment' in issue:
                normalised_issues.append({
                    'severity': issue.get('severity', 'suggestion'),
                    'file_path': issue.get('file_path', ''),
                    'line_number': issue.get('line_number'),
                    'comment': issue.get('comment', ''),
                })

            elif 'location' in issue:
                location = issue.get('location', {})
                normalised_issues.append({
                    'severity': issue.get('severity', issue.get('type', 'suggestion')),
                    'file_path': location.get('file', ''),
                    'line_number': location.get('line'),
                    'comment': issue.get('description', issue.get('message', str(issue))),
                })

            elif 'message' in issue or 'description' in issue:
                normalised_issues.append({
                    'severity': issue.get('severity', 'suggestion'),
                    'file_path': issue.get('file', issue.get('file_path', '')),
                    'line_number': issue.get('line', issue.get('line_number')),
                    'comment': issue.get('message', issue.get('description', '')),
                })

            else:
                normalised_issues.append({
                    'severity': 'suggestion',
                    'file_path': '',
                    'line_number': None,
                    'comment': str(issue),
                })

        review_data['issues'] = normalised_issues

    except json_module.JSONDecodeError:
        review_data = {
            'summary': response_text,
            'issues': [],
            'positive_feedback': '',
        }

    comments_created = []

    summary_body = f"**AI Pre-Review Summary**\n\n{review_data.get('summary', 'No summary available.')}"

    if review_data.get('positive_feedback'):
        summary_body += f"\n\n **What's good:** {review_data['positive_feedback']}"

    if diff_truncated:
        summary_body += (
            '\n\n *This PR is large. '
            'Only the first 15,000 characters of the diff were reviewed.*'
        )

    summary_comment = Comment.objects.create(
        review_cycle=cycle,
        author=None,
        is_ai_generated=True,
        body=summary_body,
    )
    comments_created.append(summary_comment)

    severity_icons = {
        'critical':   '🔴',
        'warning':    '🟡',
        'suggestion': '🔵',
    }

    for issue in review_data.get('issues', [])[:6]:
        severity = issue.get('severity', 'suggestion')

        if severity not in severity_icons:
            severity = 'suggestion'

        icon = severity_icons[severity]
        comment_body = f"{icon} **{severity.capitalize()}**\n\n{issue.get('comment', '')}"

        comment = Comment.objects.create(
            review_cycle=cycle,
            author=None,
            is_ai_generated=True,
            body=comment_body,
            file_path=issue.get('file_path', ''),
            line_number=issue.get('line_number'),
        )
        comments_created.append(comment)


    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer
    from django.utils import timezone

    channel_layer = get_channel_layer()
    group_name = f'review_cycle_{cycle_id}_comments'

    for comment in comments_created:
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'broadcast_comment',
                'comment_id': comment.id,
                'body': comment.body,
                'author_name': 'AI Reviewer',
                'author_avatar': '',
                'file_path': comment.file_path,
                'line_number': comment.line_number,
                'is_ai_generated': True,
                'created_at': timezone.now().isoformat(),
            }
        )

    if pr.head_sha and django_settings.GITHUB_TOKEN:
        critical_count = sum(
            1 for i in review_data.get('issues', [])
            if i.get('severity') == 'critical'
        )
        issue_count = len(review_data.get('issues', []))

        github.post_commit_status(
            repo.full_name,
            pr.head_sha,
            state='failure' if critical_count > 0 else 'success',
            description=(
                f'AI found {critical_count} critical issue(s)'
                if critical_count
                else f'AI review complete — {issue_count} issue(s) found'
            ),
            context='CodeReview / AI Pre-Review',
        )

    if pr.author:
        Notification.objects.create(
            recipient=pr.author,
            notification_type=NotificationType.AI_REVIEW_READY,
            title=f'AI pre-review ready for PR #{pr.github_pr_number}',
            message=review_data.get('summary', '')[:200],
            action_url=f'/reviews/{pr.pk}/',
        )

    result_msg = (
        f'AI review complete for PR #{pr.github_pr_number}. '
        f'{len(comments_created)} comments posted.'
    )
    return result_msg