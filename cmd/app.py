import datetime
import json
import logging
import os
from base64 import b64decode
from urllib.parse import parse_qs

import boto3

from slackclient import SlackClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_LENGTH = 100
ENCRYPTED_EXPECTED_TOKEN = os.environ['KMS_ENCRYPTED_TOKEN']
expected_token = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED_EXPECTED_TOKEN))['Plaintext'].decode()

slack_token = os.environ['SLACK_TOKEN']
sc = SlackClient(slack_token)

cache = {}

def lambda_handler(event, context):
    params = parse_qs(event['body'])
    token = params['token'][0]
    if token != expected_token:
        logger.error('Request token (%s) does not match expected', token)
        return respond('Invalid request token')

    logger.info(params)
    if not is_valid_command(params):
        logger.error('Invalid command parmas: %s', params)
        return respond('''usage:
\t/ch list
\t/ch list CHANNEL_PREFIX
\t/ch search NAME or PURPOSE
        ''')

    command_text = []
    if 'text' in params:
        command_text = params['text'][0].split(' ')

    channels = exec_command(sc, command_text)
    return respond(build_message(channels))

def build_message(channels):
    length = len(channels)
    if length == 0:
        ret = 'チャンネルが見つかりませんでした。\n'
    elif not length > MAX_LENGTH:
        ret = '{length}件のチャンネルが見つかりました。\n'.format(length = length)
    else:
        ret = '{length}件のチャンネルが見つかりました。上位{max}件を表示しています。\n'.format(length = length, max = MAX_LENGTH)
        channels = channels[0:MAX_LENGTH]

    for channel in channels:
        if channel['purpose']['value']:
            ret = ret + '<#{id}|{name}> - {purpose}\n'.format(id = channel['id'], name = channel['name'], purpose = channel['purpose']['value'])
        else:
            ret = ret + '<#{id}|{name}>\n'.format(id = channel['id'], name = channel['name'])
    return ret

def is_valid_command(params):
    if 'text' in params:
        command_text = params['text'][0].split(' ')
        # /ch list, /ch list NAME_PREFIX
        if command_text[0] == 'list' and len(command_text) <= 2:
            return True
        # /ch search NAME or PURPOSE
        elif command_text[0] == 'search' and len(command_text) == 2:
            return True

    return False

def exec_command(sc, command_text):
    channels = get_channels(sc)
    # /ch list NAME_PREFIX
    if command_text[0] == 'list' and len(command_text) == 2:
        return list(filter(lambda c : c['name'].startswith(command_text[1]), channels))
    # /ch search NAME or PURPOSE
    elif command_text[0] == 'search' and len(command_text) == 2:
        return list(filter(lambda c : command_text[1] in c['name'] or command_text[1] in c['purpose']['value'], channels))
    # /ch list
    else:
        return channels

def list_channels(client):
    channels = []
    api_channels = client.api_call(
        'conversations.list',
        types = 'public_channel',
        exclude_archived = 1,
        limit = 200
    )

    if api_channels['ok']:
        channels = api_channels['channels']
        while api_channels['response_metadata']['next_cursor'] != '':
            next_cursor = api_channels['response_metadata']['next_cursor']
            api_channels = client.api_call(
                'conversations.list',
                types = 'public_channel',
                exclude_archived = 1,
                limit = 200,
                cursor = next_cursor
            )
            logger.info('api_response: ' + json.dumps(api_channels))

            if api_channels['ok']:
                channels = channels + api_channels['channels']

    channels.sort(key = lambda channel : channel['name'])
    return channels

def respond(res = None):
    return {
        'statusCode': '200',
        'body': res,
        'headers': {
            'Content-Type': 'application/json',
        },
    }

def get_channels(client, expiration_seconds = 300):
    import datetime
    global cache

    now = datetime.datetime.now()
    if ('updated' in cache
        and cache['updated'] + datetime.timedelta(seconds = expiration_seconds) > now):
        logger.info('Get from cache')
        return cache['channels']

    channels = list_channels(client)
    cache = {
        'channels': channels,
        'updated': datetime.datetime.now()
    }
    return channels