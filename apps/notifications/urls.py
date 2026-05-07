from django.urls import path
from . import views

app_name = 'notifications'

urlpatterns = [
    path('notifications/count/', views.notification_count_view, name='count'),
    path('notifications/', views.notification_list_view, name='list'),
]