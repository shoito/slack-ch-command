import json
import logging
import os
from base64 import b64decode
from urllib.parse import parse_qs

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EXEC_LAMBDA_FUNCTION_NAME = 'slack-channels-slash-cmd-exec'
ENCRYPTED_EXPECTED_TOKEN = os.environ['KMS_ENCRYPTED_TOKEN']
expected_token = boto3.client('kms').decrypt(CiphertextBlob=b64decode(ENCRYPTED_EXPECTED_TOKEN))['Plaintext'].decode()

lambda_client = boto3.client('lambda')

def lambda_handler(event, context):
    if not 'body' in event:
        return respond('Request body is empty')

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

    logger.info(command_text)
    lambda_client.invoke(
        FunctionName = EXEC_LAMBDA_FUNCTION_NAME,
        InvocationType = 'Event',
        Payload = json.dumps({
            'command_text': command_text,
            'response_url': params['response_url'][0],
        }, ensure_ascii = False)
    )

    return respond()

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

def respond(res = None):
    return {
        'statusCode': '200',
        'body': res,
        'headers': {
            'Content-Type': 'application/json',
        },
    }