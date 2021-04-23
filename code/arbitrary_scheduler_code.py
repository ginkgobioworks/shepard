# Arbitrary Scheduler Code by Jacob Mevorach

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

def submit_new_job(UUID, ZIP, sqs, queue_url, s3event):
    t_end = time.time() + 60 * 10 #try to submit a batch job successfully for 10 minutes
    submitted_successfully = False
    while time.time() < t_end:
        response = boto3.client('batch').submit_job(jobName=UUID, jobQueue=os.getenv('job_queue_name'),
                                                    jobDefinition=os.getenv('job_definition_arn'), containerOverrides={
                'environment': [{'name': 'UUID', 'value': UUID}, {'name': 'INPUT_ZIP_NAME', 'value': ZIP}, {'name': 'IS_INVOKED', 'value': 'False'}]})
        if response['ResponseMetadata']['HTTPStatusCode'] == 200:
            submitted_successfully = True
            break
    if not submitted_successfully:
        t_end = time.time() + 60 * 2  # try to submit a sqs message succesfully for 2 minutes
        submitted_successfully = False
        while time.time() < t_end:
            response = sqs.send_message(QueueUrl=queue_url, MessageBody=s3event)
            if response['ResponseMetadata']['HTTPStatusCode'] == 200:
                submitted_successfully = True
                break
        if not submitted_successfully:
            raise ValueError('Failed to send SQS message back to queue!')

def fetch(s3,bucket_name,key,start,len):
    end = start + len - 1
    return s3.get_object(Bucket=bucket_name,Key=key,Range='bytes={}-{}'.format(start, end))['Body'].read()

def parse_int(bytes):
    val = bytes[0] + (bytes[1] << 8)
    if len(bytes) > 3:
        val += (bytes[2] << 16) + (bytes[3] << 24)
    return val

def lambda_handler(event, context):
    logger.info(event)
    sqs = boto3.client('sqs')
    s3event = json.loads(event['Records'][0]['body'])
    key = s3event['Records'][0]['s3']['object']['key']
    bucket_name = s3event['Records'][0]['s3']['bucket']['name']
    queue_url = sqs.get_queue_url(QueueName=event['Records'][0]['eventSourceARN'].split(':')[-1])
    zip_obj = boto3.resource('s3').Object(bucket_name=bucket_name,key=key)
    size = zip_obj.content_length
    s3 = boto3.client('s3')
    eocd = fetch(s3,bucket_name,key, size - 22, 22)
    cd_start = parse_int(eocd[16:20])
    cd_size = parse_int(eocd[12:16])
    cd = fetch(s3,bucket_name,key,cd_start, cd_size)
    zip = zipfile.ZipFile(BytesIO(cd + eocd))
    for zi in zip.filelist:
        if zi.filename == "inputs.txt":
            file_head = fetch(s3,bucket_name,key,cd_start + zi.header_offset + 26, 4)
            name_len = parse_int(file_head[0:2])
            extra_len = parse_int(file_head[2:4])
            content = fetch(s3,bucket_name,key,cd_start + zi.header_offset + 30 + name_len + extra_len, zi.compress_size)
            if zi.compress_type == zipfile.ZIP_DEFLATED:
                data_loaded = json.loads(zlib.decompressobj(-15).decompress(content))
            else:
                data_loaded = json.loads(content)
    UUID = str(context.aws_request_id) + str(s3event['Records'][0]['responseElements']['x-amz-request-id']) + str(
        s3event['Records'][0]['s3']['object']['eTag'])
    submit_new_job(UUID, key, sqs, queue_url, s3event)
    create_item(table_name, data_loaded, UUID)
    return {
        'statusCode': 200,
        'body': json.dumps(str(os.getenv('project_name')) + ' scheduler executed successfully!')
    }
