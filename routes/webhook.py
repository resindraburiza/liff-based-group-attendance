from flask import Blueprint, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, TextMessage as LineTextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from config import LINE_CHANNEL_SECRET, LINE_CHANNEL_TOKEN, ADMIN_SECRET, BASE_URL

webhook_bp = Blueprint('webhook', __name__)

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_TOKEN)


@webhook_bp.route('/webhook', methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature', '')
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    # Only respond to direct messages (not group/room messages)
    if event.source.type != 'user':
        return

    text = event.message.text.strip()

    if text.startswith('!toyonaka-admin'):
        parts = text.split(maxsplit=1)
        password = parts[1] if len(parts) > 1 else ''

        if password == ADMIN_SECRET:
            reply_text = f"Admin panel: {BASE_URL}/liff/admin?secret={password}"
        else:
            reply_text = "Invalid password."
    else:
        # Ignore all other messages silently.
        # Uncomment the line below to send a help message instead:
        # reply_text = "Send '!toyonaka-admin <password>' to access the admin panel."
        return

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[LineTextMessage(text=reply_text)],
            )
        )
