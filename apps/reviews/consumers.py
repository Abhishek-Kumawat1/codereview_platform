import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class ReviewCommentConsumer(AsyncWebsocketConsumer):
    """
    Handles WebSocket connections for a specific review cycle's comment feed.

    """

    async def connect(self):
        """
        Called when a browser opens a WebSocket connection.
        """
        self.cycle_id = self.scope['url_route']['kwargs']['cycle_id']

        self.group_name = f'review_cycle_{self.cycle_id}_comments'

        self.user = self.scope['user']

        if not self.user.is_authenticated:
            await self.close(code=4001)
            return

        has_access = await self.check_cycle_access()
        if not has_access:
            await self.close(code=4003)
            return

        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )

        await self.accept()

        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': f'Connected to review cycle {self.cycle_id}',
            'user': self.user.display_name,
        }))

    async def disconnect(self, close_code):
        """
        Called when the browser closes the tab, loses network connection,
        or the WebSocket is closed for any reason.
        """
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    async def receive(self, text_data):
        """
        Called when the browser SENDS a message to us.
        """
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON'
            }))
            return

        message_type = data.get('type')

        if message_type == 'new_comment':
            await self.handle_new_comment(data)
        elif message_type == 'typing':
            await self.handle_typing_indicator(data)

    async def handle_new_comment(self, data):
        """
        Save a new comment and broadcast it to all connected users.
        """
        body = data.get('body', '').strip()

        if not body:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Comment body cannot be empty'
            }))
            return

        comment = await self.save_comment(
            body=body,
            file_path=data.get('file_path', ''),
            line_number=data.get('line_number'),
            parent_id=data.get('parent_id'),
        )

        await database_sync_to_async(self.queue_notification)(comment.id)

        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'broadcast_comment',
                'comment_id': comment.id,
                'body': comment.body,
                'author_name': self.user.display_name,
                'author_avatar': self.user.avatar,
                'file_path': comment.file_path,
                'line_number': comment.line_number,
                'is_ai_generated': False,
                'created_at': comment.created_at.isoformat(),
            }
        )

    async def handle_typing_indicator(self, data):
        """
        Broadcast a typing indicator to other users.
        Does NOT save to the database — purely ephemeral.
        """
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'broadcast_typing',
                'user_name': self.user.display_name,
                'is_typing': data.get('is_typing', False),
            }
        )


    async def broadcast_comment(self, event):
        """
        Called on every consumer when a new comment is broadcast to the group.
        """
        await self.send(text_data=json.dumps({
            'type': 'new_comment',
            'comment_id': event['comment_id'],
            'body': event['body'],
            'author_name': event['author_name'],
            'author_avatar': event['author_avatar'],
            'file_path': event.get('file_path', ''),
            'line_number': event.get('line_number'),
            'is_ai_generated': event.get('is_ai_generated', False),
            'created_at': event['created_at'],
        }))

    async def broadcast_typing(self, event):
        """
        Called on every consumer when someone is typing.
        """
        if event['user_name'] == self.user.display_name:
            return

        await self.send(text_data=json.dumps({
            'type': 'typing',
            'user_name': event['user_name'],
            'is_typing': event['is_typing'],
        }))

    async def broadcast_cycle_status(self, event):
        """
        Called when a reviewer submits a decision.
        """
        await self.send(text_data=json.dumps({
            'type': 'cycle_status_update',
            'status': event['status'],
            'approved_count': event['approved_count'],
            'changes_requested_count': event['changes_requested_count'],
        }))


    @database_sync_to_async
    def check_cycle_access(self):
        """
        Verify the user has permission to view this review cycle.
        """
        from apps.reviews.models import ReviewCycle
        from apps.accounts.models import Role

        try:
            cycle = ReviewCycle.objects.select_related(
                'pull_request__author',
                'pull_request__repository__owner',
            ).get(pk=self.cycle_id)
        except ReviewCycle.DoesNotExist:
            return False

        user = self.user

        if user.role == Role.ADMIN:
            return True

        if cycle.pull_request.author == user:
            return True

        if cycle.reviewer_assignments.filter(reviewer=user).exists():
            return True

        if cycle.pull_request.repository.owner == user:
            return True

        return False

    @database_sync_to_async
    def save_comment(self, body, file_path='', line_number=None, parent_id=None):
        """
        Save a comment to the database.
        Runs in a thread pool via database_sync_to_async.
        """
        from apps.reviews.models import Comment, ReviewCycle

        cycle = ReviewCycle.objects.get(pk=self.cycle_id)

        comment = Comment.objects.create(
            review_cycle=cycle,
            author=self.user,
            body=body,
            file_path=file_path or '',
            line_number=line_number,
            parent_id=parent_id,
        )
        return comment

    def queue_notification(self, comment_id):
        """
        Queue the Celery notification task.
        Called via database_sync_to_async from handle_new_comment.
        """
        from apps.notifications.tasks import send_comment_notification
        send_comment_notification.delay(comment_id)