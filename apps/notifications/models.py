from django.db import models
from django.conf import settings


class NotificationType(models.TextChoices):
    COMMENT_ADDED = 'comment_added', 'New comment on your PR'
    REVIEW_APPROVED = 'review_approved', 'Your PR was approved'
    CHANGES_REQUESTED = 'changes_requested', 'Changes requested on your PR'
    REVIEWER_ASSIGNED = 'reviewer_assigned', 'You were assigned as reviewer'
    AI_REVIEW_READY = 'ai_review_ready', 'AI pre-review is ready'


class Notification(models.Model):
    """
    An in-app notification for a user.
    """

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )

    notification_type = models.CharField(
        max_length=50,
        choices=NotificationType.choices,
    )

    title = models.CharField(max_length=255)
    message = models.TextField()

    action_url = models.CharField(max_length=500, blank=True, default='')

    is_read = models.BooleanField(default=False, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient} — {self.notification_type}'