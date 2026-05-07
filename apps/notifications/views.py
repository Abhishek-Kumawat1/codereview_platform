from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from .models import Notification


@login_required
def notification_count_view(request):
    """
    Returns the unread notification count for the navbar bell.
    """
    count = Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).count()

    if count == 0:
        return HttpResponse('')

    return HttpResponse(
        f'<span style="background:#e63946;color:white;border-radius:50%;'
        f'padding:1px 6px;font-size:.75rem;margin-left:4px;">{count}</span>'
    )


@login_required
def notification_list_view(request):
    """
    Returns the notification dropdown content.
    Marks all as read when the dropdown is opened.
    """
    notifications = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:20]

    Notification.objects.filter(
        recipient=request.user,
        is_read=False,
    ).update(is_read=True)

    return render(request, 'notifications/_notification_list.html', {
        'notifications': notifications,
    })