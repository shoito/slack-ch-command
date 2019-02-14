import datetime
import json
import logging
import os
from base64 import b64decode
from urllib.parse import parse_qs
import requests

import boto3

from slackclient import SlackClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_LENGTH = 100

slack_token = os.environ['SLACK_TOKEN']
sc = SlackClient(slack_token)

cache = {}

def lambda_handler(event, context):
    logger.info(event)

    command_text = event['command_text']
    response_url = event['response_url']

    channels = exec_command(sc, command_text)
    requests.post(response_url, json = {'text': build_message(channels)})

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
            ret = ret + '<#{id}|{name}>\n```{purpose}```\n'.format(id = channel['id'], name = channel['name'], purpose = channel['purpose']['value'].replace('```', ''))
        else:
            ret = ret + '<#{id}|{name}>\n'.format(id = channel['id'], name = channel['name'])
    return ret

def exec_command(sc, command_text):
    channels = get_channels(sc)
    # /ch list NAME_PREFIX
    if command_text[0] == 'list' and len(command_text) == 2:
        return filter_prefix(command_text[1], channels)
    # /ch search NAME or PURPOSE
    elif command_text[0] == 'search' and len(command_text) == 2:
        return search(command_text[1], channels)
    # /ch list
    else:
        return channels

def filter_prefix(prefix, channels):
    return list(filter(lambda c : c['name'].startswith(prefix), channels))

def search(term, channels):
    return list(filter(lambda c : term in c['name'] or term in c['purpose']['value'] or term in c['topic']['value'], channels))

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