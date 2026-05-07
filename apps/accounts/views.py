from django.shortcuts import render, redirect
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.views.generic import TemplateView
from django.contrib import messages
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.http import HttpResponse, JsonResponse

from .models import User, Role



def login_view(request):
    """
    Simple login page.
    """
    if request.user.is_authenticated:
        return redirect('accounts:dashboard')
    return render(request, 'accounts/login.html')


def logout_view(request):
    """
    Log out and redirect to home.
    """
    if request.method == 'POST':
        logout(request)
        messages.success(request, 'You have been logged out.')
    return redirect('/')


@login_required
def dashboard_view(request):
    """
    Main dashboard — first page after login.
    """
    return render(request, 'accounts/dashboard.html', {
        'user': request.user,
    })


@login_required
def profile_view(request):
    """
    User profile page — view and edit their own profile.
    """
    if request.method == 'POST':
        user = request.user
        user.bio = request.POST.get('bio', '')
        user.first_name = request.POST.get('first_name', '')
        user.last_name = request.POST.get('last_name', '')
        user.save()

        if request.headers.get('HX-Request'):
            messages.success(request, 'Profile updated.')
            return render(request, 'accounts/_profile_form.html', {
                'user': user
            })

        messages.success(request, 'Profile updated.')
        return redirect('accounts:profile')

    return render(request, 'accounts/profile.html', {
        'user': request.user,
    })

@login_required
def user_management_view(request):
    """
    Admin-only page for managing user roles.
    Lists all users and lets admins promote/demote roles.
    """
    if not request.user.is_admin:
        messages.error(request, 'Admin access required.')
        return redirect('accounts:dashboard')

    users = User.objects.all().order_by('-date_joined')

    return render(request, 'accounts/user_management.html', {
        'users': users,
        'roles': Role.choices,
    })


@login_required
def update_user_role_view(request, user_pk):
    """
    Update a user's role. Admin only.
    Returns updated row fragment for HTMX to swap.
    """
    if not request.user.is_admin:
        return HttpResponse('Admin access required.', status=403)

    if request.method != 'POST':
        return HttpResponse(status=405)

    try:
        target_user = User.objects.get(pk=user_pk)
    except User.DoesNotExist:
        return HttpResponse('User not found.', status=404)

    new_role = request.POST.get('role')
    if new_role not in Role.values:
        return HttpResponse('Invalid role.', status=400)

    if target_user == request.user and new_role != Role.ADMIN:
        return HttpResponse(
            '<span style="color:#991b1b;">Cannot demote yourself.</span>',
            status=400
        )

    target_user.role = new_role
    target_user.save(update_fields=['role'])

    if request.headers.get('HX-Request'):
        return render(request, 'accounts/_user_row.html', {
            'u': target_user,
            'roles': Role.choices,
            'current_user': request.user,
        })

    messages.success(request, f'Updated {target_user.display_name} to {new_role}')
    return redirect('accounts:user_management')

@login_required
def dashboard_view(request):
    from apps.reviews.models import PullRequest, ReviewCycle, PRStatus, CycleStatus
    from django.db import models as db_models

    user = request.user

    open_reviews = PullRequest.objects.filter(
        author=user,
        status=PRStatus.OPEN,
    ).count()

    pending_review = PullRequest.objects.filter(
        review_cycles__reviewer_assignments__reviewer=user,
        review_cycles__status__in=[
            CycleStatus.PENDING,
            CycleStatus.IN_PROGRESS,
        ]
    ).distinct().count()

    approved_count = PullRequest.objects.filter(
        author=user,
        status=PRStatus.APPROVED,
    ).count()

    from apps.reviews.models import Comment
    recent_comments = Comment.objects.filter(
        review_cycle__pull_request__author=user,
    ).exclude(
        author=user,
    ).select_related(
        'author',
        'review_cycle__pull_request',
    ).order_by('-created_at')[:10]

    return render(request, 'accounts/dashboard.html', {
        'user': user,
        'open_reviews': open_reviews,
        'pending_review': pending_review,
        'approved_count': approved_count,
        'recent_comments': recent_comments,
    })


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extend the default JWT serializer to include user data in the response.
    When an API client logs in, they get their token AND their user info
    in one request instead of having to make a second call.
    """
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'email': self.user.email,
            'display_name': self.user.display_name,
            'role': self.user.role,
            'avatar': self.user.avatar,
        }
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer