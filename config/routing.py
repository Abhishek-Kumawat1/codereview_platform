"""
WebSocket URL routing.
"""
from django.urls import re_path
from apps.reviews.consumers import ReviewCommentConsumer

websocket_urlpatterns = [
    re_path(r'^ws/reviews/(?P<cycle_id>\d+)/comments/$', ReviewCommentConsumer.as_asgi()),
]