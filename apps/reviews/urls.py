from django.urls import path
from . import views

app_name = 'reviews'

urlpatterns = [
    path('', views.pull_request_list_view, name='pr_list'),
    path('reviews/count/', views.dashboard_count_view, name='dashboard_count'),
    path('reviews/<int:pk>/', views.pull_request_detail_view, name='pr_detail'),
    path('reviews/cycle/<int:cycle_pk>/comments/', views.add_comment_view, name='add_comment'),
    path('reviews/cycle/<int:cycle_pk>/decision/', views.submit_review_decision_view, name='submit_decision'),
    path('reviews/cycle/<int:cycle_pk>/ai-review/', views.trigger_ai_review_view, name='trigger_ai_review'),
    path('reviews/cycle/<int:cycle_pk>/reviewers/search/', views.search_reviewers_view, name='search_reviewers'),
    path('reviews/cycle/<int:cycle_pk>/reviewers/assign/', views.assign_reviewer_view, name='assign_reviewer'),
    path('reviews/cycle/<int:cycle_pk>/reviewers/remove/<int:user_pk>/', views.remove_reviewer_view, name='remove_reviewer'),
]