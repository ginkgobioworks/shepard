# Arbitrary Job Batching Endpoint Code by Jacob Mevorach

import uuid
import datetime
import time
import json
import boto3
import logging
import os
import shutil
from io import BytesIO
import zipfile
import sys
import zlib
import base64
import ast

logger = logging.getLogger()
logger.setLevel(logging.INFO)

table_name = os.getenv('dynamodb_table_name')

def common_member(a, b):
    a_set = set(a)
    b_set = set(b)
    if len(a_set.intersection(b_set)) > 0:
        return (True)
    return (False)

def create_item(table_name, data_loaded, UUID):
    dynamodb_resource = boto3.resource('dynamodb')

    table = dynamodb_resource.Table(table_name)

    item = {}
    for k, v in data_loaded.items():
        item[k] = v

    if common_member(ast.literal_eval(os.getenv('reserved_keywords')),[x.upper() for x in data_loaded.keys()]):
        raise ValueError('You used a reserved keyword in this job json.')

    item = {}
    item['UUID'] = UUID
    item['END_TIME'] = int((datetime.datetime.now()+datetime.timedelta(days=int(str(os.getenv('days_to_keep_failed_launch_indexes'))))).timestamp())
    item['START_TIME'] = 'not_yet_initiated'
    item['JOB_STATUS'] = 'not_yet_initiated'

    for k, v in data_loaded.items():
        item[k] = v

    with table.batch_writer() as batch:
        response = batch.put_item(
            Item=item
        )

    return 0

def submit_new_job(UUID):
    t_end = time.time() + 60 * 10 #try to submit a batch job successfully for 10 minutes
    submitted_successfully = False
    while time.time() < t_end:
        response = boto3.client('batch').submit_job(jobName=UUID, jobQueue=os.getenv('job_queue_name'),
                                                    jobDefinition=os.getenv('job_definition_arn'), containerOverrides={
                'environment': [{'name': 'UUID', 'value': UUID}, {'name': 'INPUT_ZIP_NAME', 'value': 'None'}, {'name': 'IS_INVOKED', 'value': 'True'}]})
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            submitted_successfully = True
            break
    if not submitted_successfully:
        raise ValueError('Failed to submit job to batch queue!')

def lambda_handler(event, context):
    logger.info(event)
    data_loaded = event
    UUID = str(context.aws_request_id) + str(base64.b16encode(str.encode(str(event))).decode("utf-8"))[:50]
    submit_new_job(UUID)
    create_item(table_name, data_loaded, UUID)
    return {
        'statusCode': 200,
        'body': json.dumps(str(os.getenv('project_name')) + ' scheduler executed successfully!')
    }
