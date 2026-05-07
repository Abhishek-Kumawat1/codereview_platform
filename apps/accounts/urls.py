from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('profile/', views.profile_view, name='profile'),

    path('users/', views.user_management_view, name='user_management'),
    path('users/<int:user_pk>/role/', views.update_user_role_view, name='update_role'),

    path('api/token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain'),

    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
]