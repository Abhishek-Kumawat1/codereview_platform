from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Role


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Custom admin for our User model.
    """
    list_display = [
        'email', 'display_name', 'role',
        'github_username', 'is_active', 'date_joined'
    ]
    list_filter = ['role', 'is_active', 'is_staff']
    search_fields = ['email', 'github_username', 'first_name', 'last_name']
    ordering = ['-date_joined']

    fieldsets = BaseUserAdmin.fieldsets + (
        ('GitHub', {
            'fields': ('github_username', 'github_id', 'avatar_url', 'github_connected_at')
        }),
        ('Platform', {
            'fields': ('role', 'bio')
        }),
    )