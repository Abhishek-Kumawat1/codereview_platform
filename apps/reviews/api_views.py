from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import models

from .models import PullRequest, ReviewCycle, PRStatus, CycleStatus
from .serializers import (
    PullRequestSerializer,
    PullRequestListSerializer,
    ReviewCycleSerializer,
)


class PullRequestListAPIView(generics.ListAPIView):
    """
    GET /api/reviews/
    Returns all PRs the authenticated user is involved with.    """
    serializer_class = PullRequestListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = PullRequest.objects.filter(
            models.Q(author=user) |
            models.Q(review_cycles__reviewer_assignments__reviewer=user)
        ).select_related(
            'author', 'repository'
        ).distinct().order_by('-created_at')

        status = self.request.query_params.get('status')
        if status and status in PRStatus.values:
            queryset = queryset.filter(status=status)

        return queryset


class PullRequestDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/reviews/<pk>/
    Returns full PR detail including current cycle, comments, reviewers.
    """
    serializer_class = PullRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        return PullRequest.objects.filter(
            models.Q(author=user) |
            models.Q(review_cycles__reviewer_assignments__reviewer=user) |
            models.Q(repository__owner=user)
        ).select_related(
            'author', 'repository'
        ).prefetch_related(
            'review_cycles__reviewer_assignments__reviewer',
            'review_cycles__comments__author',
        ).distinct()


class ReviewCycleDetailAPIView(generics.RetrieveAPIView):
    """
    GET /api/cycles/<pk>/
    Returns a specific review cycle with all comments and assignments.
    """
    serializer_class = ReviewCycleSerializer
    permission_classes = [permissions.IsAuthenticated]
    queryset = ReviewCycle.objects.prefetch_related(
        'reviewer_assignments__reviewer',
        'comments__author',
    )


class DashboardStatsAPIView(APIView):
    """
    GET /api/stats/
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({
            'open_reviews': PullRequest.objects.filter(
                author=user,
                status=PRStatus.OPEN,
            ).count(),
            'pending_your_review': PullRequest.objects.filter(
                review_cycles__reviewer_assignments__reviewer=user,
                review_cycles__status__in=[
                    CycleStatus.PENDING,
                    CycleStatus.IN_PROGRESS,
                ]
            ).distinct().count(),
            'approved_this_week': PullRequest.objects.filter(
                author=user,
                status=PRStatus.APPROVED,
            ).count(),
            'total_comments_given': user.comments.filter(
                is_ai_generated=False
            ).count(),
        })