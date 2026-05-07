import hashlib
import hmac
import json

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages

from .models import Repository
from apps.reviews.models import (
    PullRequest, ReviewCycle, ReviewerAssignment,
    PRStatus, CycleStatus
)


@csrf_exempt
@require_POST
def github_webhook_view(request, repo_id):
    """
    Receives webhook events from GitHub for a specific repository.

    @csrf_exempt: webhooks come from GitHub's servers.

    @require_POST: only POST requests are valid. GET requests to this
                   URL return 405 Method Not Allowed.

    repo_id: the github_repo_id stored in our Repository model.
    """

    try:
        repo = Repository.objects.get(github_repo_id=repo_id)
    except Repository.DoesNotExist:

        return HttpResponse(status=404)

    if not _validate_github_signature(request, repo.webhook_secret):
        return HttpResponse('Invalid signature.', status=403)

    event_type = request.headers.get('X-GitHub-Event', '')

    if event_type == 'ping':
        return JsonResponse({'message': 'pong'})

    if event_type != 'pull_request':
        return JsonResponse({'message': f'Event {event_type} ignored'})

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse('Invalid JSON.', status=400)

    action = payload.get('action', '')

    pr_data = payload.get('pull_request', {})

    if not pr_data:
        return HttpResponse('No pull_request in payload.', status=400)

    handlers = {
        'opened': _handle_pr_opened,
        'closed': _handle_pr_closed,
        'synchronize': _handle_pr_synchronize,
        'reopened': _handle_pr_reopened,
    }

    handler = handlers.get(action)
    if handler:
        handler(repo, pr_data, payload)

    return JsonResponse({'message': f'Action {action} processed'})


def _validate_github_signature(request, secret):
    """
    Validates the HMAC-SHA256 signature GitHub sends with every webhook.

    Returns True if valid, False if invalid or missing.
    """
    if not secret:
        return not settings.DEBUG is False

    signature_header = request.headers.get('X-Hub-Signature-256', '')

    if not signature_header.startswith('sha256='):
        return False

    received_signature = signature_header[7:]

    expected_signature = hmac.new(
    key=secret.encode('utf-8'),
    msg=request.body,
    digestmod=hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(expected_signature, received_signature)


def _handle_pr_opened(repo, pr_data, payload):
    """
    A new PR was opened on GitHub.
    Creates our PullRequest record and starts the first ReviewCycle.
    """
    from apps.accounts.models import User

    github_author = pr_data.get('user', {})
    author = User.objects.filter(
        github_id=str(github_author.get('id', ''))
    ).first()

    def parse_dt(dt_str):
        if not dt_str:
            return None
        from django.utils.dateparse import parse_datetime
        return parse_datetime(dt_str)

    pr, created = PullRequest.objects.get_or_create(
        github_pr_id=str(pr_data['id']),
        defaults={
            'repository': repo,
            'author': author,
            'github_pr_number': pr_data['number'],
            'title': pr_data['title'],
            'body': pr_data.get('body') or '',
            'head_branch': pr_data['head']['ref'],
            'base_branch': pr_data['base']['ref'],
            'head_sha': pr_data['head']['sha'],
            'status': PRStatus.OPEN,
            'github_created_at': parse_dt(pr_data.get('created_at')),
            'github_updated_at': parse_dt(pr_data.get('updated_at')),
        }
    )

    if not created:
        return

    cycle = ReviewCycle.objects.create(
        pull_request=pr,
        cycle_number=1,
        status=CycleStatus.PENDING,
    )

    pr.status = PRStatus.IN_REVIEW
    pr.save(update_fields=['status'])

    from apps.notifications.tasks import run_ai_review
    run_ai_review.delay(cycle.id)


def _handle_pr_closed(repo, pr_data, payload):
    """
    PR was closed — either merged or just closed without merging.
    """
    try:
        pr = PullRequest.objects.get(github_pr_id=str(pr_data['id']))
    except PullRequest.DoesNotExist:
        return

    if pr_data.get('merged'):
        pr.status = PRStatus.MERGED
        pr.github_merged_at = timezone.now()
    else:
        pr.status = PRStatus.CLOSED

    pr.github_updated_at = timezone.now()
    pr.save(update_fields=['status', 'github_merged_at', 'github_updated_at'])

    pr.review_cycles.filter(
        status__in=[CycleStatus.PENDING, CycleStatus.IN_PROGRESS]
    ).update(status=CycleStatus.CANCELLED)


def _handle_pr_synchronize(repo, pr_data, payload):
    """
    New commits were pushed to the PR branch.

    """
    try:
        pr = PullRequest.objects.get(github_pr_id=str(pr_data['id']))
    except PullRequest.DoesNotExist:
        return

    pr.head_sha = pr_data['head']['sha']
    pr.github_updated_at = timezone.now()
    pr.save(update_fields=['head_sha', 'github_updated_at'])

    open_cycles = pr.review_cycles.filter(
        status__in=[CycleStatus.PENDING, CycleStatus.IN_PROGRESS]
    )
    cancelled_count = open_cycles.update(status=CycleStatus.CANCELLED)

    if cancelled_count > 0:
        last_cycle_number = pr.review_cycles.order_by(
            '-cycle_number'
        ).values_list('cycle_number', flat=True).first() or 0

        ReviewCycle.objects.create(
            pull_request=pr,
            cycle_number=last_cycle_number + 1,
            status=CycleStatus.PENDING,
        )


def _handle_pr_reopened(repo, pr_data, payload):
    """PR was reopened after being closed."""
    try:
        pr = PullRequest.objects.get(github_pr_id=str(pr_data['id']))
    except PullRequest.DoesNotExist:
        return

    pr.status = PRStatus.OPEN
    pr.save(update_fields=['status'])


@login_required
def repository_list_view(request):
    """Lists all repositories the current user has connected."""
    repos = Repository.objects.filter(
        owner=request.user
    ).order_by('-created_at')

    return render(request, 'repositories/repo_list.html', {
        'repositories': repos,
    })


@login_required
def repository_connect_view(request):
    """
    Connects a GitHub repository to our platform.
    """
    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()

        if '/' not in full_name:
            messages.error(request, 'Please enter the full repo name, e.g. username/repo')
            return redirect('repositories:connect')

        owner_name, repo_name = full_name.split('/', 1)

        repo, created = Repository.objects.get_or_create(
            github_repo_id=f'manual_{full_name.replace("/", "_")}',
            defaults={
                'owner': request.user,
                'name': repo_name,
                'full_name': full_name,
                'default_branch': 'main',
            }
        )

        if created:
            repo.generate_webhook_secret()
            messages.success(
                request,
                f'Repository {full_name} connected. '
                f'Configure your GitHub webhook to point to the URL below.'
            )
        else:
            messages.info(request, f'Repository {full_name} already connected.')

        return redirect('repositories:detail', pk=repo.pk)

    return render(request, 'repositories/repo_connect.html')


@login_required
def repository_detail_view(request, pk):
    """
    Shows repository details and webhook configuration instructions.
    """
    repo = get_object_or_404(Repository, pk=pk, owner=request.user)

    webhook_url = (
        f"{settings.SITE_URL}/webhooks/{repo.github_repo_id}/"
    )

    return render(request, 'repositories/repo_detail.html', {
        'repo': repo,
        'webhook_url': webhook_url,
    })


@login_required
def trigger_ai_review_view(request, cycle_pk):
    """
    Manually trigger an AI pre-review for a review cycle.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)

    user = request.user
    is_author = cycle.pull_request.author == user
    is_reviewer = cycle.reviewer_assignments.filter(reviewer=user).exists()

    if not (is_author or is_reviewer or user.is_admin):
        return HttpResponse('Permission denied.', status=403)

    from apps.notifications.tasks import run_ai_review
    run_ai_review.delay(cycle.id)

    if request.headers.get('HX-Request'):
        return HttpResponse(
            '<span style="color:#065f46;">✓ AI review queued — '
            'comments will appear shortly.</span>'
        )

    messages.success(request, 'AI review queued. Comments will appear shortly.')
    return redirect('reviews:pr_detail', pk=cycle.pull_request_id)


