from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    """
    TextChoices creates an enum that stores as a string in the database.
    """
    AUTHOR = 'author', 'Author'           
    REVIEWER = 'reviewer', 'Reviewer'     
    ADMIN = 'admin', 'Admin'              


class User(AbstractUser):
    """
    Custom User model for the code review platform.
    """

    email = models.EmailField(unique=True)

    github_username = models.CharField(
        max_length=100,
        blank=True,    
        null=False,         
        default='',
    )
    github_id = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text='GitHub user ID — stable even if username changes'

    )
    avatar_url = models.URLField(
        blank=True,
        default='',
        help_text='GitHub avatar URL'
    )


    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.AUTHOR,
    )


    bio = models.TextField(blank=True, default='')

    github_connected_at = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    class Meta:
        db_table = 'accounts_user'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
        ordering = ['-date_joined']

    def __str__(self):
        return self.email


    @property
    def is_reviewer(self):
        return self.role in (Role.REVIEWER, Role.ADMIN)

    @property
    def is_admin(self):
        return self.role == Role.ADMIN

    @property
    def display_name(self):
        """
        Best available name to show in the UI.
        """
        if self.get_full_name():
            return self.get_full_name()
        if self.github_username:
            return self.github_username
        return self.email.split('@')[0]

    @property
    def avatar(self):
        """
        Return avatar URL or a deterministic placeholder.
        """
        if self.avatar_url:
            return self.avatar_url
        return f'https://api.dicebear.com/7.x/initials/svg?seed={self.display_name}'