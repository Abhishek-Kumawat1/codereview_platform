import secrets
from django.db import models
from django.conf import settings


class Repository(models.Model):
    """
    A GitHub repository linked to our platform.
    """

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='repositories',
    )

    github_repo_id = models.CharField(
        max_length=100,
        unique=True,
        help_text='GitHub repository ID — stable across renames'
    )
    name = models.CharField(max_length=200)

    full_name = models.CharField(max_length=300)

    description = models.TextField(blank=True, default='')

    is_private = models.BooleanField(default=False)

    default_branch = models.CharField(max_length=100, default='main')

    webhook_secret = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='HMAC secret for validating GitHub webhook payloads'
    )
    webhook_id = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text='GitHub webhook ID — used to manage the webhook via API'
    )
    is_webhook_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'repositories'
        verbose_name_plural = 'Repositories'
        ordering = ['-created_at']

    def __str__(self):
        return self.full_name

    def generate_webhook_secret(self):
        """
        Generate a cryptographically secure random secret for this repo's webhook.
        """
        self.webhook_secret = secrets.token_hex(32)
        self.save(update_fields=['webhook_secret'])
        return self.webhook_secret