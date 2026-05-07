from django.contrib import admin
from .models import PullRequest, ReviewCycle, ReviewerAssignment, Comment


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ['title', 'repository', 'author', 'status', 'created_at']
    list_filter = ['status']
    search_fields = ['title', 'github_pr_number']
    readonly_fields = ['created_at', 'updated_at']


class ReviewerAssignmentInline(admin.TabularInline):
    """
    Show reviewer assignments directly inside the ReviewCycle admin page.
    """
    model = ReviewerAssignment
    extra = 1


@admin.register(ReviewCycle)
class ReviewCycleAdmin(admin.ModelAdmin):
    list_display = ['pull_request', 'cycle_number', 'status', 'created_at']
    list_filter = ['status']
    inlines = [ReviewerAssignmentInline]
    readonly_fields = ['created_at', 'updated_at', 'completed_at']


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ['author', 'review_cycle', 'is_ai_generated', 'created_at']
    list_filter = ['is_ai_generated']
    search_fields = ['body']