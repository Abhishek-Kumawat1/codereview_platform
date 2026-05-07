from django.urls import path
from . import views

app_name = 'repositories'

urlpatterns = [
    path('', views.repository_list_view, name='list'),
    path('connect/', views.repository_connect_view, name='connect'),
    path('<int:pk>/', views.repository_detail_view, name='detail'),
]