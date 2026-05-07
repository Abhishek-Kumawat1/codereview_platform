from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.adapter import DefaultAccountAdapter
from django.utils import timezone


class AccountAdapter(DefaultAccountAdapter):
    """
    Customises allauth's default account behaviour.
    """
    def save_user(self, request, user, form, commit=True):
        user = super().save_user(request, user, form, commit=False)
        if commit:
            user.save()
        return user


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """
    Runs after a successful GitHub OAuth login.
    """

    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)

        github_data = sociallogin.account.extra_data

        user.github_username = github_data.get('login', '')

        user.github_id = str(github_data.get('id', ''))

        user.avatar_url = github_data.get('avatar_url', '')

        full_name = github_data.get('name', '')
        if full_name and not user.get_full_name():
            parts = full_name.split(' ', 1)
            user.first_name = parts[0]
            user.last_name = parts[1] if len(parts) > 1 else ''

        user.github_connected_at = timezone.now()
        user.save()

        return user