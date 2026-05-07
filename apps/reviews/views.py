from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.contrib import messages
from django.utils import timezone
from django.db import models

from .models import PullRequest, ReviewCycle, ReviewerAssignment, Comment
from .models import PRStatus, CycleStatus, ReviewDecision
from apps.accounts.models import User, Role
from apps.notifications.tasks import (
    send_comment_notification,
    send_review_decision_notification,
)
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

@login_required
def dashboard_count_view(request):
    """
    Returns just the count of open PRs for the dashboard lazy load.
    """
    count = PullRequest.objects.filter(
        repository__owner=request.user,
        status=PRStatus.OPEN,
    ).count()
    return HttpResponse(str(count))


@login_required
def pull_request_list_view(request):
    """
    List all PRs the current user is involved with —
    either as author or as an assigned reviewer.
    """
    user = request.user

    authored = PullRequest.objects.filter(
        author=user
    ).select_related('repository', 'author')

    reviewing = PullRequest.objects.filter(
        review_cycles__reviewer_assignments__reviewer=user,
        review_cycles__status__in=[
            CycleStatus.PENDING,
            CycleStatus.IN_PROGRESS,
        ]
    ).select_related('repository', 'author').distinct()

    return render(request, 'reviews/pr_list.html', {
        'authored_prs': authored,
        'reviewing_prs': reviewing,
    })


@login_required
def pull_request_detail_view(request, pk):
    """
    Detail view for a single PR — shows all review cycles and comments.
    This page also sets up the WebSocket connection for live comments.
    """
    pr = get_object_or_404(
        PullRequest.objects.select_related(
            'repository', 'author'
        ).prefetch_related(
            'review_cycles__reviewer_assignments__reviewer',
            'review_cycles__comments__author',
        ),
        pk=pk
    )
    user = request.user
    is_author = pr.author == user
    is_reviewer = pr.review_cycles.filter(
        reviewer_assignments__reviewer=user
    ).exists()
    is_admin = user.is_admin

    if not (is_author or is_reviewer or is_admin):
        messages.error(request, 'You do not have access to this PR.')
        return redirect('reviews:pr_list')

    current_cycle = pr.current_cycle

    return render(request, 'reviews/pr_detail.html', {
        'pr': pr,
        'current_cycle': current_cycle,
        'is_author': is_author,
        'is_reviewer': is_reviewer,
    })


@login_required
def add_comment_view(request, cycle_pk):
    """
    Add a comment to a review cycle.
    Handles both HTMX requests (returns comment fragment)
    and regular POST requests (redirects).
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)
    body = request.POST.get('body', '').strip()

    if not body:
        if request.headers.get('HX-Request'):
            return HttpResponse(
                '<p style="color:red">Comment cannot be empty.</p>',
                status=400
            )
        messages.error(request, 'Comment cannot be empty.')
        return redirect('reviews:pr_detail', pk=cycle.pull_request_id)

    comment = Comment.objects.create(
        review_cycle=cycle,
        author=request.user,
        body=body,
        file_path=request.POST.get('file_path', ''),
        line_number=request.POST.get('line_number') or None,
        parent_id=request.POST.get('parent_id') or None,
    )

    send_comment_notification.delay(comment.id)

    if request.headers.get('HX-Request'):
        return render(request, 'reviews/_comment.html', {
            'comment': comment
        })

    return redirect('reviews:pr_detail', pk=cycle.pull_request_id)


@login_required
def submit_review_decision_view(request, cycle_pk):
    if request.method != 'POST':
        return HttpResponse(status=405)

    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)
    decision = request.POST.get('decision')

    if decision not in ReviewDecision.values:
        return HttpResponse('Invalid decision.', status=400)

    assignment, created = ReviewerAssignment.objects.get_or_create(
        review_cycle=cycle,
        reviewer=request.user,
    )
    assignment.decision = decision
    assignment.reviewed_at = timezone.now()
    assignment.save()

    cycle.update_status()

    send_review_decision_notification.delay(assignment.id)

    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f'review_cycle_{cycle_pk}_comments',
        {
            'type': 'broadcast_cycle_status',
            'status': cycle.status,
            'approved_count': cycle.approved_count,
            'changes_requested_count': cycle.changes_requested_count,
        }
    )

    if request.headers.get('HX-Request'):
        return render(request, 'reviews/_cycle_status.html', {'cycle': cycle})

    messages.success(request, f'Review submitted: {decision}')
    return redirect('reviews:pr_detail', pk=cycle.pull_request_id)

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
            '<span style="color:#065f46;"> AI review queued — '
            'comments will appear shortly.</span>'
        )

    messages.success(request, 'AI review queued. Comments will appear shortly.')
    return redirect('reviews:pr_detail', pk=cycle.pull_request_id)


@login_required
def search_reviewers_view(request, cycle_pk):
    """
    Search for users to assign as reviewers.
    """
    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return HttpResponse('')

    from apps.accounts.models import Role

    already_assigned = cycle.reviewer_assignments.values_list(
        'reviewer_id', flat=True
    )

    users = User.objects.filter(
        role__in=[Role.REVIEWER, Role.ADMIN],
    ).exclude(
        pk__in=already_assigned,
    ).filter(
        models.Q(github_username__icontains=query) |
        models.Q(first_name__icontains=query) |
        models.Q(last_name__icontains=query) |
        models.Q(email__icontains=query)
    )[:8]

    return render(request, 'reviews/_reviewer_search_results.html', {
        'users': users,
        'cycle': cycle,
    })


@login_required
def assign_reviewer_view(request, cycle_pk):
    """
    Assign a user as a reviewer on a review cycle.
    Only PR authors, existing reviewers, and admins can assign.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)
    user_id = request.POST.get('user_id')

    if not user_id:
        return HttpResponse('No user specified.', status=400)

    requester = request.user
    is_author = cycle.pull_request.author == requester
    is_reviewer = cycle.reviewer_assignments.filter(reviewer=requester).exists()

    if not (is_author or is_reviewer or requester.is_admin):
        return HttpResponse('Permission denied.', status=403)

    try:
        reviewer = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return HttpResponse('User not found.', status=404)

    assignment, created = ReviewerAssignment.objects.get_or_create(
        review_cycle=cycle,
        reviewer=reviewer,
    )

    if created:
        from apps.notifications.tasks import send_reviewer_assigned_notification
        send_reviewer_assigned_notification.delay(assignment.id)

    return render(request, 'reviews/_reviewers_section.html', {
        'cycle': cycle,
        'is_author': is_author,
        'is_reviewer': True,
    })


@login_required
def remove_reviewer_view(request, cycle_pk, user_pk):
    """
    Remove a reviewer assignment from a cycle.
    Only the PR author or admins can remove reviewers.
    """
    if request.method != 'POST':
        return HttpResponse(status=405)

    cycle = get_object_or_404(ReviewCycle, pk=cycle_pk)

    if cycle.pull_request.author != request.user and not request.user.is_admin:
        return HttpResponse('Permission denied.', status=403)

    ReviewerAssignment.objects.filter(
        review_cycle=cycle,
        reviewer_id=user_pk,
    ).delete()

    is_author = cycle.pull_request.author == request.user

    return render(request, 'reviews/_reviewers_section.html', {
        'cycle': cycle,
        'is_author': is_author,
        'is_reviewer': cycle.reviewer_assignments.filter(
            reviewer=request.user
        ).exists(),
    })