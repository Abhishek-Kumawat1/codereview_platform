from rest_framework import serializers
from .models import PullRequest, ReviewCycle, ReviewerAssignment, Comment


class CommentSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(
        source='author.display_name',
        read_only=True,
        default='AI Reviewer'
    )

    class Meta:
        model = Comment
        fields = [
            'id', 'body', 'author_name', 'file_path',
            'line_number', 'is_ai_generated', 'is_inline',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ReviewerAssignmentSerializer(serializers.ModelSerializer):
    reviewer_name = serializers.CharField(
        source='reviewer.display_name',
        read_only=True
    )
    reviewer_avatar = serializers.CharField(
        source='reviewer.avatar',
        read_only=True
    )

    class Meta:
        model = ReviewerAssignment
        fields = [
            'id', 'reviewer_name', 'reviewer_avatar',
            'decision', 'assigned_at', 'reviewed_at',
        ]
        read_only_fields = fields


class ReviewCycleSerializer(serializers.ModelSerializer):
    reviewer_assignments = ReviewerAssignmentSerializer(many=True, read_only=True)
    comments = CommentSerializer(many=True, read_only=True)

    class Meta:
        model = ReviewCycle
        fields = [
            'id', 'cycle_number', 'status',
            'approved_count', 'changes_requested_count',
            'reviewer_assignments', 'comments',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class PullRequestSerializer(serializers.ModelSerializer):
    author_name = serializers.CharField(
        source='author.display_name',
        read_only=True
    )
    repository_name = serializers.CharField(
        source='repository.full_name',
        read_only=True
    )
    current_cycle = ReviewCycleSerializer(read_only=True)
    github_url = serializers.CharField(read_only=True)

    class Meta:
        model = PullRequest
        fields = [
            'id', 'title', 'body', 'status',
            'github_pr_number', 'github_url',
            'head_branch', 'base_branch', 'head_sha',
            'author_name', 'repository_name',
            'current_cycle',
            'created_at', 'updated_at',
        ]
        read_only_fields = fields


class PullRequestListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the list endpoint.
    """
    author_name = serializers.CharField(
        source='author.display_name',
        read_only=True
    )
    repository_name = serializers.CharField(
        source='repository.full_name',
        read_only=True
    )

    class Meta:
        model = PullRequest
        fields = [
            'id', 'title', 'status', 'github_pr_number',
            'author_name', 'repository_name', 'created_at',
        ]