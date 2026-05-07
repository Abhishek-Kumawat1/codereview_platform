from django.contrib import admin
from .models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ['full_name', 'owner', 'is_private', 'is_webhook_active', 'created_at']
    list_filter = ['is_private', 'is_webhook_active']
    search_fields = ['full_name', 'name']
    readonly_fields = ['webhook_secret', 'webhook_id', 'created_at', 'updated_at']