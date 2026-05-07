
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from apps.accounts.models import User, Role
from apps.repositories.models import Repository
from apps.reviews.models import (
    PullRequest, ReviewCycle, ReviewerAssignment,
    Comment, PRStatus, CycleStatus
)


class Command(BaseCommand):
    help = 'Seeds the database with realistic test data for the most recent user'

    def add_arguments(self, parser):
        parser.add_argument(
            '--email',
            type=str,
            help='Seed data for a specific user by email. '
                 'If omitted, uses the most recently logged-in user.',
        )

    def handle(self, *args, **options):

        email = options.get('email')

        if email:
            try:
                user = User.objects.get(email=email)
            except User.DoesNotExist:
                raise CommandError(
                    f'No user found with email: {email}\n'
                    f'Existing users: {list(User.objects.values_list("email", flat=True))}'
                )
        else:
            user = User.objects.filter(
                last_login__isnull=False
            ).order_by('-last_login').first()

            if not user:
                user = User.objects.order_by('-date_joined').first()

            if not user:
                raise CommandError(
                    'No users found in the database.\n'
                    'Log in via GitHub OAuth first, then run this command.'
                )

        self.stdout.write(
            f'Seeding data for user: {user.email} '
            f'(@{user.github_username or user.username})'
        )

        if user.role == Role.AUTHOR:
            user.role = Role.REVIEWER
            user.save(update_fields=['role'])
            self.stdout.write('  → Upgraded role to Reviewer')

        repo, created = Repository.objects.get_or_create(
            github_repo_id=f'seed_repo_{user.pk}',
            defaults={
                'owner': user,
                'name': 'my-django-app',
                'full_name': f'{user.github_username or user.username}/my-django-app',
                'description': 'A Django web application — seeded for testing',
                'default_branch': 'main',
                'is_webhook_active': False,
            }
        )
        if created:
            self.stdout.write(f'  → Created repository: {repo.full_name}')
        else:
            self.stdout.write(f'  → Using existing repository: {repo.full_name}')

        pr, created = PullRequest.objects.get_or_create(
            github_pr_id=f'seed_pr_{user.pk}',
            defaults={
                'repository': repo,
                'author': user,
                'github_pr_number': 42,
                'title': 'Refactor authentication middleware',
                'body': (
                    'This PR refactors the auth middleware to use JWT tokens '
                    'instead of sessions.\n\n'
                    '**Changes:**\n'
                    '- Replaced session-based auth with JWT\n'
                    '- Added token refresh endpoint\n'
                    '- Improved API performance by ~40%\n\n'
                    '**Testing:**\n'
                    'All existing tests pass. Added 12 new unit tests.'
                ),
                'head_branch': 'feature/jwt-auth',
                'base_branch': 'main',
                'head_sha': 'abc123def456abc123def456abc123def456abc1',
                'status': PRStatus.IN_REVIEW,
                'github_created_at': timezone.now(),
            }
        )
        if created:
            self.stdout.write(f'  → Created PR #{pr.github_pr_number}: {pr.title}')
        else:
            self.stdout.write(f'  → Using existing PR #{pr.github_pr_number}')

        cycle, created = ReviewCycle.objects.get_or_create(
            pull_request=pr,
            cycle_number=1,
            defaults={'status': CycleStatus.IN_PROGRESS}
        )

        ReviewerAssignment.objects.get_or_create(
            review_cycle=cycle,
            reviewer=user,
        )

        if created:
            self.stdout.write(f'  → Created review cycle #{cycle.cycle_number}')

        if not cycle.comments.exists():
            Comment.objects.create(
                review_cycle=cycle,
                author=user,
                body='Overall this looks good. The JWT implementation is clean and well tested.',
            )
            Comment.objects.create(
                review_cycle=cycle,
                author=user,
                body='Can we add rate limiting to the token refresh endpoint? '
                     'Worried about brute force attacks if tokens are short-lived.',
                file_path='apps/accounts/views.py',
                line_number=47,
            )
            Comment.objects.create(
                review_cycle=cycle,
                author=user,
                body='Minor: the variable name `tkn` on line 83 should be `token` for readability.',
                file_path='apps/accounts/views.py',
                line_number=83,
            )

            Comment.objects.create(
                review_cycle=cycle,
                author=None,
                is_ai_generated=True,
                body=(
                    '**AI Pre-Review Summary**\n\n'
                    '- Token expiry (60min) may be too long for sensitive operations. '
                    'Consider 15min for admin actions.\n'
                    '- No test coverage for the token blacklist edge case.\n'
                    '- `SECRET_KEY` is referenced directly in views.py line 91 — '
                    'should use `settings.SECRET_KEY` instead.'
                ),
            )
            self.stdout.write('  → Created 4 comments (including 1 AI review)')

        self.stdout.write(self.style.SUCCESS(
            f'\nDone! Visit these URLs:\n'
            f'  PR list:   http://localhost/\n'
            f'  PR detail: http://localhost/reviews/{pr.pk}/\n'
            f'  Admin:     http://localhost/admin/\n'
        ))