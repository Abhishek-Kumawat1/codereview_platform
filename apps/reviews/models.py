from django.db import models
from django.conf import settings


class PRStatus(models.TextChoices):
    """
    The lifecycle of a Pull Request on our platform.
    """
    OPEN = 'open', 'Open'
    IN_REVIEW = 'in_review', 'In Review'
    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
    APPROVED = 'approved', 'Approved'
    MERGED = 'merged', 'Merged'
    CLOSED = 'closed', 'Closed'


class CycleStatus(models.TextChoices):
    """
    The status of one review cycle.
    """
    PENDING = 'pending', 'Pending'

    IN_PROGRESS = 'in_progress', 'In Progress'

    APPROVED = 'approved', 'Approved'

    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'

    CANCELLED = 'cancelled', 'Cancelled'


class ReviewDecision(models.TextChoices):
    """
    What a reviewer decides at the end of their review.
    """
    APPROVED = 'approved', 'Approved'
    CHANGES_REQUESTED = 'changes_requested', 'Changes Requested'
    COMMENTED = 'commented', 'Commented'


class PullRequest(models.Model):
    """
    A GitHub Pull Request submitted for review on our platform.
    """

    repository = models.ForeignKey(
        'repositories.Repository',
        on_delete=models.CASCADE,
        related_name='pull_requests',
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='authored_prs',
    )

    github_pr_number = models.IntegerField()

    github_pr_id = models.CharField(max_length=100, unique=True)

    title = models.CharField(max_length=500)
    body = models.TextField(blank=True, default='')

    head_branch = models.CharField(max_length=200)

    base_branch = models.CharField(max_length=200, default='main')

    head_sha = models.CharField(max_length=40, blank=True, default='')

    status = models.CharField(
        max_length=30,
        choices=PRStatus.choices,
        default=PRStatus.OPEN,
        db_index=True,
    )

    github_created_at = models.DateTimeField(null=True, blank=True)
    github_updated_at = models.DateTimeField(null=True, blank=True)
    github_merged_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'pull_requests'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['repository', 'github_pr_number'],
                name='unique_pr_per_repo'
            )
        ]

    def __str__(self):
        return f'PR #{self.github_pr_number}: {self.title}'

    @property
    def current_cycle(self):
        """
        The active review cycle for this PR.
        """
        return self.review_cycles.exclude(
            status=CycleStatus.CANCELLED
        ).order_by('-cycle_number').first()

    @property
    def github_url(self):
        repo = self.repository
        return f'https://github.com/{repo.full_name}/pull/{self.github_pr_number}'


class ReviewCycle(models.Model):
    """
    One round of review on a Pull Request.

    When a PR is first submitted, cycle 1 begins.
    If changes are requested and the author pushes new commits
    and re-requests review, cycle 2 begins (cycle 1 is cancelled).

    """

    pull_request = models.ForeignKey(
        PullRequest,
        on_delete=models.CASCADE,
        related_name='review_cycles',
    )

    cycle_number = models.PositiveIntegerField(default=1)

    status = models.CharField(
        max_length=30,
        choices=CycleStatus.choices,
        default=CycleStatus.PENDING,
        db_index=True,
    )

    reviewers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='ReviewerAssignment',
        related_name='assigned_cycles',
    )

    approved_count = models.PositiveIntegerField(default=0)
    changes_requested_count = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'review_cycles'
        ordering = ['-cycle_number']
        constraints = [
            models.UniqueConstraint(
                fields=['pull_request', 'cycle_number'],
                name='unique_cycle_per_pr'
            )
        ]

    def __str__(self):
        return f'{self.pull_request} — Cycle {self.cycle_number}'

    def update_status(self):
        """
        Recalculate and save the cycle status based on reviewer decisions.
        Called after any reviewer submits a decision.
        """
        assignments = self.reviewer_assignments.all()

        if not assignments.exists():
            return

        decisions = [a.decision for a in assignments if a.decision]

        if ReviewDecision.CHANGES_REQUESTED in decisions:
            self.status = CycleStatus.CHANGES_REQUESTED
        elif decisions and all(d == ReviewDecision.APPROVED for d in decisions):
            self.status = CycleStatus.APPROVED
        else:
            self.status = CycleStatus.IN_PROGRESS

        self.approved_count = decisions.count(ReviewDecision.APPROVED)
        self.changes_requested_count = decisions.count(
            ReviewDecision.CHANGES_REQUESTED
        )
        self.save(update_fields=[
            'status', 'approved_count',
            'changes_requested_count', 'updated_at'
        ])


class ReviewerAssignment(models.Model):
    """
    The junction table between ReviewCycle and User (reviewers).

    """

    review_cycle = models.ForeignKey(
        ReviewCycle,
        on_delete=models.CASCADE,
        related_name='reviewer_assignments',
    )

    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='review_assignments',
    )

    decision = models.CharField(
        max_length=30,
        choices=ReviewDecision.choices,
        blank=True,
        default='',
    )

    assigned_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'reviewer_assignments'
        constraints = [
            models.UniqueConstraint(
                fields=['review_cycle', 'reviewer'],
                name='unique_reviewer_per_cycle'
            )
        ]

    def __str__(self):
        return f'{self.reviewer} on {self.review_cycle}'


class Comment(models.Model):
    """
    A comment left during a review cycle.

    """

    review_cycle = models.ForeignKey(
        ReviewCycle,
        on_delete=models.CASCADE,
        related_name='comments',
    )

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='comments',
    )

    body = models.TextField()

    file_path = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text='File path this comment is attached to, e.g. src/auth/views.py'
    )
    line_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Line number in the file this comment refers to'
    )

    is_ai_generated = models.BooleanField(
        default=False,
        db_index=True,
        help_text='True if this comment was generated by the AI pre-reviewer'
    )

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='replies',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'comments'
        ordering = ['created_at']

    def __str__(self):
        preview = self.body[:50] + '...' if len(self.body) > 50 else self.body
        return f'{self.author}: {preview}'

    @property
    def is_inline(self):
        return bool(self.file_path and self.line_number)

    @property
    def is_reply(self):
        return self.parent_id is not None