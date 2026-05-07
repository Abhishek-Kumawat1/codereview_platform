"""
Root URL configuration.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from apps.repositories.views import github_webhook_view
from apps.reviews.api_views import (
    PullRequestListAPIView,
    PullRequestDetailAPIView,
    ReviewCycleDetailAPIView,
    DashboardStatsAPIView,
)

urlpatterns = [
    path('', include('apps.notifications.urls')),
    path('admin/', admin.site.urls),

    path('accounts/', include('apps.accounts.urls')),

    path('accounts/', include('allauth.urls')),

    path('', include('apps.reviews.urls')),
    path('repositories/', include('apps.repositories.urls')),
    path('webhooks/<str:repo_id>/', github_webhook_view, name='github_webhook'),

    path('api/reviews/', PullRequestListAPIView.as_view(), name='api_pr_list'),
    path('api/reviews/<int:pk>/', PullRequestDetailAPIView.as_view(), name='api_pr_detail'),
    path('api/cycles/<int:pk>/', ReviewCycleDetailAPIView.as_view(), name='api_cycle_detail'),
    path('api/stats/', DashboardStatsAPIView.as_view(), name='api_stats'),
    path('api/auth/', include('rest_framework.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)