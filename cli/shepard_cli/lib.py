import os
import shutil
import uuid
from subprocess import call, check_output, CalledProcessError
import boto3
import traceback
from boto3.s3.transfer import TransferConfig
import multiprocessing
import base64
import json
from distutils.dir_util import copy_tree
import subprocess
import unicodedata
import re
from awscli.clidriver import create_clidriver
import io
import time

version_number = 1.21

def parse_inputs(command,minimum_variables_to_be_declared,maximum_variables_to_be_declared,variables_exempt_from_parsing,initial_context,current_context):
    enforce_minimum_variable_declarations(command,minimum_variables_to_be_declared,current_context)
    enforce_maximum_variable_declarations(command,maximum_variables_to_be_declared,variables_exempt_from_parsing,initial_context)
    return 0

def enforce_minimum_variable_declarations(command,minimum_variables_to_be_declared,current_context):
    for variable in minimum_variables_to_be_declared:
        if current_context[variable] == None:
            raise ValueError('For the command ' + '"' + command + '"' + ' the variable ' + '"' + variable + '"' + ' must be given a value. Currently it does not have a value set.')
        else:
            pass

    return 0

def enforce_maximum_variable_declarations(command,maximum_variables_to_be_declared,variables_exempt_from_parsing,initial_context):
    list_of_variables_to_scan = []

    for variable in initial_context.keys():
        if variable == 'command':
            continue
        if variable not in maximum_variables_to_be_declared and variable not in variables_exempt_from_parsing:
            list_of_variables_to_scan.append(variable)
        else:
            pass

    for variable in list_of_variables_to_scan:
        if initial_context[variable] != None:
            raise ValueError('The command ' + '"' + command + '"' + ' has no options for the variable ' + '"' + variable + '"' + ' which should not be set for this command. Currently it has a value of: ' + str(initial_context[variable]) + '.')
        else:
            pass

    return 0

def get_session(region, access_id, secret_key, secret_token = None):
    if not secret_token:
        return boto3.session.Session(region_name=region,
                                    aws_access_key_id=access_id,
                                    aws_secret_access_key=secret_key)
    else:
        return boto3.session.Session(region_name=region,
                                    aws_access_key_id=access_id,
                                    aws_secret_access_key=secret_key,
                                    aws_session_token=secret_token)

def activate_role_vars_if_exists():
    #Get home directory
    home = os.path.expanduser("~")

    #If there's a file named shepard_cli_role_credentials.txt in the .aws folder in the home directory we're going to continue.
    if os.path.exists(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt")):
        pass
    else:
        return #The file with our credentials didn't exist so return. No need to actviate any credentials.

    #read lines from file into array
    with open(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt")) as file:
        array = file.readlines()

    #Parse array for variables
    newsession_id = array[0].strip()
    newsession_key = array[1].strip()
    newsession_token = array[2].strip()

    # SET NEW ENVRIONMENT
    env = os.environ.copy()
    env['LC_CTYPE'] = u'en_US.UTF'
    env['AWS_ACCESS_KEY_ID'] = newsession_id
    env['AWS_SECRET_ACCESS_KEY'] = newsession_key
    env['AWS_SESSION_TOKEN'] = newsession_token
    os.environ.update(env)
    return env

def unset_role_vars_on_error():
    check_output('unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN', shell=True)
    return

def set_role(account_number,role_to_assume_to_target_account,mfa_token,serial_number):

    ACCOUNT_NUMBER = account_number
    IAM_ROLE = role_to_assume_to_target_account

    #Get home directory
    home = os.path.expanduser("~")

    if os.path.exists(os.path.join(home, '.aws')):
        pass
    else:
        raise ValueError('There is no .aws directory in the home directory possibly because the aws cli is not installed. This must be rectified before the set_role command can be used.')

    boto_sts = boto3.client('sts')

    #ASSUME ROLE
    if mfa_token:
        print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
        stsresponse = boto_sts.assume_role(
            RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
            RoleSessionName=str(uuid.uuid4()),
            SerialNumber=serial_number,
            TokenCode=mfa_token
        )
    else:
        print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
        stsresponse = boto_sts.assume_role(
            RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
            RoleSessionName=str(uuid.uuid4())
        )

    # Save the details from assumed role into vars
    newsession_id = stsresponse["Credentials"]["AccessKeyId"]
    newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
    newsession_token = stsresponse["Credentials"]["SessionToken"]

    # Write to file
    with open(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt"),'w+') as file:
        file.write(newsession_id+'\n')
        file.write(newsession_key+'\n')
        file.write(newsession_token+'\n')
        file.write(ACCOUNT_NUMBER+'\n')
        file.write(IAM_ROLE+'\n')

    print('Role successfully set!')
    return

def check_role():
    #Get home directory
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt")):
        print('Role file is detected. If you suspect this role file is corrupted please consider running "shepard_cli release_role" to clear the current role file.')
        with open(os.path.join(home, '.aws', "shepard_cli_role_credentials.txt")) as file:
            array = file.readlines()
        print('Currently assumed role into account ' + array[3].strip() + ' as IAM role named ' + array[4].strip() +'.')
    else:
        print('No role file is detected!')
    return

def release_role():
    #Get home directory
    home = os.path.expanduser("~")
    if os.path.exists(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt")):
        os.remove(os.path.join(home,'.aws',"shepard_cli_role_credentials.txt"))
        print('Role released!')
    else:
        print('No role is currently set!')
    return

def check_for_updates():
    try:
        check_output('git clone https://github.com/ginkgobioworks/shepard',shell=True)
    except:
        try:
            check_output('git clone git@github.com:ginkgobioworks/shepard.git',shell=True)
        except:
            print('Could not check for update. No ssh or https access to the shepard_cli repo in github.com was detected.')
            return 0
    f = open("shepard/cli/version.txt", "r")
    version_number_from_source = float(f.readline().strip())
    if version_number_from_source > version_number:
        print('Version number ' + str(version_number_from_source) + ' is the most up to date version of shepard_cli. Updating you from your current version of ' +str(version_number) +'.')
        shutil.move(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'temp_store', 'shepard', 'cli', 'shepard_cli', 'lib.py'),os.path.join(os.path.dirname(os.path.realpath(__file__)), 'lib.py'))
        shutil.move(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'temp_store', 'shepard', 'cli', 'shepard_cli', 'cli.py'),os.path.join(os.path.dirname(os.path.realpath(__file__)), 'cli.py'))
        print('Upgrade completed!')
        print('You are now running version '+str(version_number_from_source)+' which is the most up to date version of shepard_cli! Congrats!')
    else:
        print('You are running version '+str(version_number)+' which is the most up to date version of shepard_cli! Congrats!')
    shutil.rmtree("shepard")
    return 0

def check_for_environment_variables(account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, s3_bucket_for_results, directory_to_sync_s3_bucket_to, lambda_to_invoke):
    if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'current_shepard_profile_config.txt')):
        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'current_shepard_profile_config.txt'),
                  'r') as config_file:
            current_profile = config_file.read().strip()
    else:
        return account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, s3_bucket_for_results, directory_to_sync_s3_bucket_to, lambda_to_invoke #no profile was set!

    profile_not_found = True
    for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
        if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
            if file == current_profile:
                profile_not_found = False

    if profile_not_found:
        print('Profile named ' + current_profile + ' pointed at in current_shepard_profile_config.txt was not detected in the list of available profiles.')
        print('Here is a list of profiles we have detected:')
        print('######PROFILE LIST START########')

        for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
            if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                print(file)

        print('######PROFILE LIST END########')
        print('Please rectify the problem either programmatically using the CLI or by configuring files manually in the following directory: ' + str(os.path.join(os.path.dirname(os.path.realpath(__file__)))))
        print('Until the problem is rectified you will not be able to access environment variables stored in profile files and default values for inputs will be returned.')
        print('You can also clear your current profile config to rectify this problem at any time by running "shepard_cli clear_profile_config".')
        return account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, s3_bucket_for_results, directory_to_sync_s3_bucket_to, lambda_to_invoke

    with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), current_profile), 'r') as profile_file:
        data = json.loads(profile_file.read())

    if account_number == None:
        try:
            account_number = str(data['shepard_cli_account_number'])
        except:
            account_number = None

    if role_to_assume_to_target_account == None:
        try:
            role_to_assume_to_target_account = str(data['shepard_cli_role_to_assume_to_target_account'])
        except:
            role_to_assume_to_target_account = None

    if path_to_docker_folder == None:
        try:
            path_to_docker_folder = str(data['shepard_cli_path_to_docker_folder'])
        except:
            path_to_docker_folder = None

    if ecr_repo_to_push_to == None:
        try:
            ecr_repo_to_push_to = str(data['shepard_cli_ecr_repo_to_push_to'])
        except:
            ecr_repo_to_push_to = None

    if path_to_local_folder_to_batch == None:
        try:
            path_to_local_folder_to_batch = str(data['shepard_cli_path_to_local_folder_to_batch'])
        except:
            path_to_local_folder_to_batch = None

    if s3_bucket_to_upload_to == None:
        try:
            s3_bucket_to_upload_to = str(data['shepard_cli_s3_bucket_to_upload_to'])
        except:
            s3_bucket_to_upload_to = None

    if dynamo_db_to_query == None:
        try:
            dynamo_db_to_query = str(data['shepard_cli_dynamo_db_to_query'])
        except:
            dynamo_db_to_query = None

    if cloudformation_to_describe == None:
        try:
            cloudformation_to_describe = str(data['shepard_cli_cloudformation_to_describe'])
        except:
            cloudformation_to_describe = None

    if path_to_local_secrets == None:
        try:
            path_to_local_secrets = str(data['shepard_cli_path_to_local_secrets'])
        except:
            path_to_local_secrets = None

    if secret_store == None:
        try:
            secret_store = str(data['shepard_cli_secret_store'])
        except:
            secret_store = None

    if s3_bucket_for_results == None:
        try:
            s3_bucket_for_results = str(data['shepard_cli_s3_bucket_for_results'])
        except:
            s3_bucket_for_results = None

    if directory_to_sync_s3_bucket_to == None:
        try:
            directory_to_sync_s3_bucket_to = str(data['shepard_cli_directory_to_sync_s3_bucket_to'])
        except:
            directory_to_sync_s3_bucket_to = None

    if lambda_to_invoke == None:
        try:
            lambda_to_invoke = str(data['shepard_cli_lambda_to_invoke'])
        except:
            lambda_to_invoke = None

    return account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, s3_bucket_for_results, directory_to_sync_s3_bucket_to, lambda_to_invoke



######################################################DEPLOY LIBRARIES START HERE######################################################
def slugify(slug):
	slug = unicodedata.normalize('NFKD', slug)
	slug = str(slug.encode('ascii', 'ignore').lower())
	slug = re.sub(r'[^a-z0-9]+', '-', slug).strip('-')
	slugified_slug = str(re.sub(r'[-]+', '-', slug))
	slugified_slug = (slugified_slug[:250] + '..') if len(slugified_slug) > 250 else slugified_slug
	return slugified_slug

def fetch_latest_worker_container_code():

    if os.path.exists(os.path.join(os.getcwd(),'arbitrary_worker_code.py')):
        os.remove(os.path.join(os.getcwd(),'arbitrary_worker_code.py'))
    if os.path.exists(os.path.join(os.getcwd(),'Dockerfile.txt')):
        os.remove(os.path.join(os.getcwd(),'Dockerfile.txt'))

    try:
        if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)),'shepard')):
            shutil.rmtree(os.path.join(os.path.dirname(os.path.realpath(__file__)),'shepard'))
        result = subprocess.call('git clone https://github.com/ginkgobioworks/shepard.git',cwd=os.path.dirname(os.path.realpath(__file__)),shell=True)
        if result != 0:
            raise ValueError('"git clone https://github.com/ginkgobioworks/shepard.git" returned a non-zero return code.')
        shutil.copy(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'shepard', 'code', 'arbitrary_worker_code.py'),os.path.join(os.getcwd(), 'arbitrary_worker_code.py'))
        shutil.copy(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'shepard', 'code', 'Dockerfile.txt'),os.path.join(os.getcwd(), 'Dockerfile.txt'))
    except Exception as error:
        print('Could not connect to https://github.com/ginkgobioworks/shepard. Using cached worker code from the time this repo was cloned.')
        shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), 'code', 'arbitrary_worker_code.py'),os.path.join(os.getcwd(), 'arbitrary_worker_code.py'))
        shutil.copy(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__)))), 'code', 'Dockerfile.txt'),os.path.join(os.getcwd(), 'Dockerfile.txt'))

    return 0

def build_nested_container(path_to_docker_folder):
    if os.path.exists(os.path.join(os.getcwd(),'docker_folder')):
        shutil.rmtree(os.path.join(os.getcwd(),'docker_folder'))

    UUID = str(uuid.uuid4)

    copy_tree(path_to_docker_folder,os.path.join(os.getcwd(),'docker_folder'))

    try:
        result = subprocess.call('docker rm --force ' + slugify(path_to_docker_folder) + '_instance ', shell=True)
    except:
        pass

    try:
        result = subprocess.call('docker build --no-cache -f Dockerfile.txt -t '+slugify(path_to_docker_folder)+':latest .',shell=True)

        if result != 0:
            raise ValueError('Docker build command failed. Could not build initial worker container. Process is being aborted.')

    except:
        try:
            result = subprocess.call('docker build --no-cache -f Dockerfile -t '+slugify(path_to_docker_folder)+':latest .',shell=True)

            if result != 0:
                raise ValueError('Docker build command failed. Could not build initial worker container. Process is being aborted.')

        except Exception as error:
            traceback.print_tb(error.__traceback__)
            print('Could not deploy. Docker was not properly configured or no file named "Dockerfile.txt" or "Dockerfile" was found in the path to deploy from.')
            raise ValueError(str(error))

    result = subprocess.call('docker run --name '+slugify(path_to_docker_folder)+'_instance --privileged=true -v /var/run/docker.sock:/var/run/docker.sock '+slugify(path_to_docker_folder),shell=True)

    if result != 0:
        raise ValueError('Docker run command failed. Could not build nested payload container. Process is being aborted.')

    result = subprocess.call('docker commit --change="CMD python3 arbitrary_worker_code.py" '+slugify(path_to_docker_folder)+'_instance '+slugify(path_to_docker_folder)+':latest',shell=True)

    if result != 0:
        raise ValueError('Docker commit command failed. Could not commit payload container to new target image. Process is being aborted.')

    result = subprocess.call('docker rm --force '+slugify(path_to_docker_folder)+'_instance ',shell=True)

    if result != 0:
        Print('WARNING: Docker rm command failed. Could not remove dangling instance of container from host computer. Be sure to bring this up to developers and keep an eye on your docker memory usage over time.')

    return 0


def push_to_ecr(account_number,role_to_assume_to_target_account,ecr_repo_to_push_to,path_to_docker_folder,dont_assume,mfa_token,serial_number):
    region = check_output('aws configure get region',shell=True).strip().decode("utf-8")
    ACCOUNT_NUMBER = account_number
    IAM_ROLE = role_to_assume_to_target_account
    REPOSITORY_URL = ACCOUNT_NUMBER + r'.dkr.ecr.'+region+'.amazonaws.com/'  # should end in a slash
    DESTINATION_CONTAINER_NAME = ecr_repo_to_push_to

    activate_role_vars_if_exists()

    # where the programmatic push to ECR repo happens
    ##################################################################################################################
    if dont_assume == 'False':
        boto_sts = boto3.client('sts')

        if mfa_token:
            print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
            stsresponse = boto_sts.assume_role(
                RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                RoleSessionName=str(uuid.uuid4()),
                SerialNumber=serial_number,
                TokenCode=mfa_token
            )
        else:
            print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
            stsresponse = boto_sts.assume_role(
                RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                RoleSessionName=str(uuid.uuid4())
            )

        # Save the details from assumed role into vars
        newsession_id = stsresponse["Credentials"]["AccessKeyId"]
        newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
        newsession_token = stsresponse["Credentials"]["SessionToken"]

        # Here I create an ecr client using the assumed creds.
        ecr_assumed_client = get_session(
            region,
            newsession_id,
            newsession_key,
            newsession_token
        ).client('ecr')
    else:
        # Here I create an ecr client using the envrionment creds.
        ecr_assumed_client = boto3.session.Session(region_name=region).client('ecr')

    # get authorization token
    response = ecr_assumed_client.get_authorization_token(
        registryIds=[
            ACCOUNT_NUMBER,
        ]
    )

    #GET READY TO MOVE THINGS
    folder_that_contains_this_script = os.path.dirname(os.path.realpath(__file__))
    os.chdir(folder_that_contains_this_script)

    #get auth token
    auth_token = base64.b64decode(response['authorizationData'][0]['authorizationToken']).decode("utf-8")[4:] #CUT OFF THE INITIAL AWS!

    #push the recently built image
    subprocess.call(r"docker login -u AWS -p "+auth_token+" "+REPOSITORY_URL,shell=True)
    subprocess.call(r"docker tag "+slugify(path_to_docker_folder)+":latest "+REPOSITORY_URL+DESTINATION_CONTAINER_NAME,shell=True)
    subprocess.call("docker push "+REPOSITORY_URL+DESTINATION_CONTAINER_NAME,shell=True)

    return 0

def deploy(account_number,role_to_assume_to_target_account,path_to_docker_folder,ecr_repo_to_push_to,dont_assume,mfa_token,serial_number):

    print('fetching latest worker container code ...')
    try:
        fetch_latest_worker_container_code()
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('fetching latest worker container code failed')
        raise ValueError(str(error))
    print('fetching latest worker container code succeeded')

    print('building shepard style nested container ...')
    try:
        build_nested_container(path_to_docker_folder)
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('building shepard style nested container failed')
        raise ValueError(str(error))
    print('building shepard style nested container succeeded')

    print('pushing ECR to target container named ' +ecr_repo_to_push_to+'...')
    try:
        push_to_ecr(account_number,role_to_assume_to_target_account,ecr_repo_to_push_to,path_to_docker_folder,dont_assume,mfa_token,serial_number)
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('pushing ECR to target container named ' +ecr_repo_to_push_to+' failed')
        raise ValueError(str(error))
    print('pushing ECR to target container named ' +ecr_repo_to_push_to+' succeeded')
    return
######################################################DEPLOY LIBRARIES END HERE######################################################

######################################################BATCH LIBRARIES START HERE######################################################
def upload_and_return_download_link(client, file_name, bucket, object_name=None):

    # If S3 object_name was not specified, use file_name
    if object_name is None:
        object_name = file_name

    config = TransferConfig(max_concurrency=multiprocessing.cpu_count())

    # Upload the file
    file = open(os.path.join(os.getcwd(),file_name), 'rb')
    buf = io.BytesIO(file.read())
    start = time.time()
    print("starting to upload file {} to bucket {}".format(file_name, bucket))
    client.upload_fileobj(buf, bucket, object_name, Config=config)
    end = time.time()
    print("finished uploading file {} to bucket {}. time: {}".format(file_name, bucket, end - start))
    return 0

def lint_json(filename):
    try:
        with open(filename) as f:
            test = json.load(f)
            return 0
    except ValueError as e:
        print('json error found in inputs.txt file!')
        raise e

def batch(account_number,role_to_assume_to_target_account,path_to_local_folder_to_batch,s3_bucket_to_upload_to,zip_name_override,dont_assume,mfa_token,serial_number):

    activate_role_vars_if_exists()

    try:
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account
        UUID = str(uuid.uuid4())

        # where the programmatic push to s3 repo happens
        ##################################################################################################################
        if dont_assume == 'False':
            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # Here I create a s3 client using the assumed creds.
            s3_assumed_client = get_session(
                region,
                newsession_id,
                newsession_key,
                newsession_token
            ).client('s3')
        else:
            # Here I create a s3 client using environment creds.
            s3_assumed_client = boto3.session.Session(region_name=region).client('s3')

        if not os.path.exists(os.path.join(path_to_local_folder_to_batch,'inputs.txt')):
            raise ValueError('No file named "inputs.txt" was detected in the target folder. The batch command is being aborted.')

        # if json is incorrectly formatted in the inputs.txt file throw an error.
        lint_json(os.path.join(path_to_local_folder_to_batch,'inputs.txt'))

        print('copying data locally into compressed archive with name ' + UUID + '.zip')

        # object_tag = base64.b64encode(open(os.path.join(path_to_local_folder_to_batch, "inputs.txt"), 'rb').read()).decode('utf-8')
        shutil.make_archive(os.path.join(os.getcwd(),UUID), 'zip', path_to_local_folder_to_batch)

        print('pushing zip to target bucket named ' + s3_bucket_to_upload_to + '...')

        if zip_name_override == None:
            upload_and_return_download_link(s3_assumed_client, UUID+'.zip', s3_bucket_to_upload_to, object_name=None)
        else:
            if os.path.splitext(zip_name_override)[1] != '.zip':
                zip_name_override = zip_name_override + '.zip'
                print('Zip name override did not end in .zip. Appending now.')
            upload_and_return_download_link(s3_assumed_client, UUID+'.zip', s3_bucket_to_upload_to, object_name=zip_name_override)

        os.remove(UUID+'.zip')
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('pushing zip to target bucket named ' +s3_bucket_to_upload_to+' failed')
        raise ValueError(str(error))
    print('pushing zip to target bucket named ' +s3_bucket_to_upload_to+' succeeded')
    return
######################################################BATCH LIBRARIES END HERE######################################################

######################################################QUERY LIBRARIES START HERE######################################################
def query(account_number,role_to_assume_to_target_account,dynamo_db_to_query,dont_assume,mfa_token,serial_number):
    print('attempting to query dynamoDB named ' + dynamo_db_to_query + '...')

    activate_role_vars_if_exists()

    try:
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account

        # where the programmatic dynamoDB query happens
        ##################################################################################################################
        if dont_assume == 'False':
            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # Here I create an dynamodb resource using the assumed creds.
            dynamoDB_assumed_resource = get_session(
                region,
                newsession_id,
                newsession_key,
                newsession_token
            ).resource('dynamodb')
        else:
            # Here I create an dynamodb resource using environment creds.
            dynamoDB_assumed_resource = boto3.session.Session(region_name=region).resource('dynamodb')

        table = dynamoDB_assumed_resource.Table(dynamo_db_to_query)
        store_dict = {}

        scan = table.scan()
        for item in scan['Items']:
            print(item)
            store_dict[item['UUID']] = str(item)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('dynamoDB query to target bucket named ' +dynamo_db_to_query+' failed')
        raise ValueError(str(error))
    print('dynamoDB query to target bucket named ' +dynamo_db_to_query+' succeeded. A dictionary object containing the scanned contents of the database has been returned.')
    return store_dict
######################################################QUERY LIBRARIES END HERE######################################################

######################################################DESCRIBE LIBRARIES START HERE######################################################
def describe(account_number,role_to_assume_to_target_account,cloudformation_to_describe,dont_assume,mfa_token,serial_number):
    print('attempting to describe stack named ' + cloudformation_to_describe + '...')

    activate_role_vars_if_exists()

    try:
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account

        # where the programmatic cloudformation query happens
        ##################################################################################################################
        if dont_assume == 'False':
            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # Here I create a cloudformation client using the assumed creds.
            cloudformation_assumed_client = get_session(
                region,
                newsession_id,
                newsession_key,
                newsession_token
            ).client('cloudformation')
        else:
            # Here I create a cloudformation client using environment creds.
            cloudformation_assumed_client = boto3.session.Session(region_name=region).client('cloudformation')

        response = cloudformation_assumed_client.describe_stacks(StackName=cloudformation_to_describe)

        print(response)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('attempt to describe stack named ' + cloudformation_to_describe + ' failed.')
        raise ValueError(str(error))
    print('attempt to describe stack named ' + cloudformation_to_describe + ' succeeded. The response from the cloudformation client has been returned.')
    return response
######################################################DESCRIBE LIBRARIES STOP HERE######################################################

######################################################SECRETIFY LIBRARIES START HERE######################################################
def secretify(account_number,role_to_assume_to_target_account,path_to_local_secrets,secret_store,dont_assume,mfa_token,serial_number):
    print('attempting to deploy secrets located in ' + path_to_local_secrets + ' to ' + secret_store + '...')

    activate_role_vars_if_exists()

    try:
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account

        # where the programmatic secrets manager upload happens
        ##################################################################################################################
        if dont_assume == 'False':
            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # Here I create a s3 client using the assumed creds.
            secretsmanager_assumed_client = get_session(
                region,
                newsession_id,
                newsession_key,
                newsession_token
            ).client('secretsmanager')
        else:
            # Here I create a s3 client using environment creds.
            secretsmanager_assumed_client = boto3.session.Session(region_name=region).client('secretsmanager')

        secrets_dictionary = {}

        #Get new secrets string from directory of secrets
        for item in os.listdir(path_to_local_secrets):
            if os.path.isfile(os.path.join(path_to_local_secrets, item)):
                data = base64.b64encode(open(os.path.join(path_to_local_secrets,item), 'rb').read()).decode('utf-8')
                secrets_dictionary[item] = data


        if not secrets_dictionary:
            print('There were no files in that directory to upload! No action was performed.')
            return

        response = secretsmanager_assumed_client.update_secret(
            SecretId=secret_store,
            SecretString=json.dumps(secrets_dictionary),
        )

        print(response)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('attempt to deploy secrets located in ' + path_to_local_secrets + ' to ' + secret_store + ' failed.')
        raise ValueError(str(error))
    print('attempt to deploy secrets located in ' + path_to_local_secrets + ' to ' + secret_store + ' succeeded.')
    return
######################################################SECRETIFY LIBRARIES STOP HERE######################################################

######################################################CONFIGURE LIBRARIES START HERE######################################################
def configure(profile_name):

    print('Configuration command initiated!')

    print('')
    print("\033[4m" + 'IMPORTANT NOTICE STARTS HERE!' + "\033[0m")
    print('REMEMBER TO FILL OUT ALL OF THE FORMS USING THE COMMAND "aws configure" AS WELL OR THIS CLI WILL NOT PROPERLY FUNCTION!')
    print("\033[4m" + 'IMPORTANT NOTICE ENDS HERE!' + "\033[0m")
    print('')

    try:

        if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)),profile_name)):
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),profile_name),'r') as profile_file:
                data = json.loads(profile_file.read())
            profile_exists = True
        else:
            data = {}
            profile_exists = False

        if profile_exists:
            try:
                account_number = data['shepard_cli_account_number']
            except:
                account_number = ''
            user_input = input('shepard_cli_account_number['+account_number+']:').strip()
        else:
            user_input = input('shepard_cli_account_number[]:').strip()
        if user_input:
            data['shepard_cli_account_number']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_account_number']=''

        if profile_exists:
            try:
                role_to_assume_to_target_account = data['shepard_cli_role_to_assume_to_target_account']
            except:
                role_to_assume_to_target_account = ''
            user_input = input('shepard_cli_role_to_assume_to_target_account['+role_to_assume_to_target_account+']:').strip()
        else:
            user_input = input('shepard_cli_role_to_assume_to_target_account[]:').strip()
        if user_input:
            data['shepard_cli_role_to_assume_to_target_account']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_role_to_assume_to_target_account']=''

        if profile_exists:
            try:
                path_to_docker_folder = data['shepard_cli_path_to_docker_folder']
            except:
                path_to_docker_folder = ''
            user_input = input('shepard_cli_path_to_docker_folder['+path_to_docker_folder+']:').strip()
        else:
            user_input = input('shepard_cli_path_to_docker_folder[]:').strip()
        if user_input:
            data['shepard_cli_path_to_docker_folder']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_path_to_docker_folder']=''

        if profile_exists:
            try:
                ecr_repo_to_push_to = data['shepard_cli_ecr_repo_to_push_to']
            except:
                ecr_repo_to_push_to = ''
            user_input = input('shepard_cli_ecr_repo_to_push_to['+ecr_repo_to_push_to+']:').strip()
        else:
            user_input = input('shepard_cli_ecr_repo_to_push_to[]:').strip()
        if user_input:
            data['shepard_cli_ecr_repo_to_push_to']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_ecr_repo_to_push_to']=''

        if profile_exists:
            try:
                path_to_local_folder_to_batch = data['shepard_cli_path_to_local_folder_to_batch']
            except:
                path_to_local_folder_to_batch = ''
            user_input = input('shepard_cli_path_to_local_folder_to_batch['+path_to_local_folder_to_batch+']:').strip()
        else:
            user_input = input('shepard_cli_path_to_local_folder_to_batch[]:').strip()
        if user_input:
            data['shepard_cli_path_to_local_folder_to_batch']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_path_to_local_folder_to_batch']=''

        if profile_exists:
            try:
                s3_bucket_to_upload_to = data['shepard_cli_s3_bucket_to_upload_to']
            except:
                s3_bucket_to_upload_to = ''
            user_input = input('shepard_cli_s3_bucket_to_upload_to['+s3_bucket_to_upload_to+']:').strip()
        else:
            user_input = input('shepard_cli_s3_bucket_to_upload_to[]:').strip()
        if user_input:
            data['shepard_cli_s3_bucket_to_upload_to']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_s3_bucket_to_upload_to']=''

        if profile_exists:
            try:
                dynamo_db_to_query = data['shepard_cli_dynamo_db_to_query']
            except:
                dynamo_db_to_query = ''
            user_input = input('shepard_cli_dynamo_db_to_query['+dynamo_db_to_query+']:').strip()
        else:
            user_input = input('shepard_cli_dynamo_db_to_query[]:').strip()
        if user_input:
            data['shepard_cli_dynamo_db_to_query']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_dynamo_db_to_query']=''

        if profile_exists:
            try:
                cloudformation_to_describe = data['shepard_cli_cloudformation_to_describe']
            except:
                cloudformation_to_describe = ''
            user_input = input('shepard_cli_cloudformation_to_describe['+cloudformation_to_describe+']:').strip()
        else:
            user_input = input('shepard_cli_cloudformation_to_describe[]:').strip()
        if user_input:
            data['shepard_cli_cloudformation_to_describe']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_cloudformation_to_describe']=''

        if profile_exists:
            try:
                path_to_local_secrets = data['shepard_cli_path_to_local_secrets']
            except:
                path_to_local_secrets = ''
            user_input = input('shepard_cli_path_to_local_secrets['+path_to_local_secrets+']:').strip()
        else:
            user_input = input('shepard_cli_path_to_local_secrets[]:').strip()
        if user_input:
            data['shepard_cli_path_to_local_secrets']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_path_to_local_secrets']=''

        if profile_exists:
            try:
                secret_store = data['shepard_cli_secret_store']
            except:
                secret_store = ''
            user_input = input('shepard_cli_secret_store['+secret_store+']:').strip()
        else:
            user_input = input('shepard_cli_secret_store[]:').strip()
        if user_input:
            data['shepard_cli_secret_store']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_secret_store']=''

        if profile_exists:
            try:
                s3_bucket_for_results = data['shepard_cli_s3_bucket_for_results']
            except:
                s3_bucket_for_results = ''
            user_input = input('shepard_cli_s3_bucket_for_results['+s3_bucket_for_results+']:').strip()
        else:
            user_input = input('shepard_cli_s3_bucket_for_results[]:').strip()
        if user_input:
            data['shepard_cli_s3_bucket_for_results']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_s3_bucket_for_results']=''

        if profile_exists:
            try:
                directory_to_sync_s3_bucket_to = data['shepard_cli_directory_to_sync_s3_bucket_to']
            except:
                directory_to_sync_s3_bucket_to = ''
            user_input = input('shepard_cli_directory_to_sync_s3_bucket_to['+directory_to_sync_s3_bucket_to+']:').strip()
        else:
            user_input = input('shepard_cli_directory_to_sync_s3_bucket_to[]:').strip()
        if user_input:
            data['shepard_cli_directory_to_sync_s3_bucket_to']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_directory_to_sync_s3_bucket_to']=''

        if profile_exists:
            try:
                lambda_to_invoke = data['shepard_cli_lambda_to_invoke']
            except:
                lambda_to_invoke = ''
            user_input = input('shepard_cli_lambda_to_invoke['+lambda_to_invoke+']:').strip()
        else:
            user_input = input('shepard_cli_lambda_to_invoke[]:').strip()
        if user_input:
            data['shepard_cli_lambda_to_invoke']=str(user_input)
        if user_input == '**CLEAR**':
            data['shepard_cli_lambda_to_invoke']=''

        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),profile_name), "w+") as outfile:
            json.dump(data, outfile)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('Configuration command failed!')
        raise ValueError(str(error))
    print('Configuration command was successful!')
    return
######################################################CONFIGURE LIBRARIES STOP HERE######################################################

######################################################CHECK PROFILE LIBRARIES START HERE######################################################
def check_profile():
    try:
        if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)),'current_shepard_profile_config.txt')):
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'current_shepard_profile_config.txt'),'r') as config_file:
                current_profile = config_file.read().strip()
            default_profile_exists = True
        else:
            default_profile_exists = False

        if default_profile_exists:
            print('DEFAULT PROFILE IS SET')
            print('######PROFILE LIST START########')
            for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
                if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                    if file == current_profile:
                        print("\033[4m"+current_profile+"\033[0m")
                    else:
                        print(file)
            print('######PROFILE LIST END########')
            print('CURRENT PROFILE ATTRIBUTES:')
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), current_profile), 'r') as profile_file:
                data = json.loads(profile_file.read())
            print(data)


        else:
            print('DEFAULT PROFILE IS NOT SET')
            print('######PROFILE LIST START########')

            for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
                if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                    print(file)

            print('######PROFILE LIST END########')


    except Exception as error:
        traceback.print_tb(error.__traceback__)
        raise ValueError(str(error))
    return
######################################################CONFIGURE LIBRARIES STOP HERE######################################################

######################################################SET PROFILE LIBRARIES START HERE######################################################
def set_profile(profile_name):
    try:
        profile_not_found = True
        for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
            if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                if file == profile_name:
                    profile_not_found = False

        if profile_not_found:
            print('Profile named '+profile_name+' was not detected as an existing profile.')
            print('Here is a list of profiles we have detected:')
            print('######PROFILE LIST START########')

            for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
                if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                    print(file)

            print('######PROFILE LIST END########')
            return

        with open(os.path.join(os.path.dirname(os.path.realpath(__file__)),'current_shepard_profile_config.txt'),'w+') as config_file:
            config_file.write(profile_name)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        raise ValueError(str(error))
    return
######################################################SET LIBRARIES STOP HERE######################################################

######################################################SET PROFILE LIBRARIES START HERE######################################################
def delete_profile(profile_name):
    try:
        profile_not_found = True
        for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
            if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                if file == profile_name:
                    profile_not_found = False

        if profile_not_found:
            print('Profile named '+profile_name+' was not detected as an existing profile.')
            print('Here is a list of profiles we have detected:')
            print('######PROFILE LIST START########')

            for file in os.listdir(os.path.join(os.path.dirname(os.path.realpath(__file__)))):
                if file not in ['lib.py', 'cli.py' ,'.DS_Store','__init__.py','__pycache__','shepard','temp_store','current_shepard_profile_config.txt']:
                    print(file)

            print('######PROFILE LIST END########')
            return

        os.remove(os.path.join(os.path.join(os.path.dirname(os.path.realpath(__file__))),profile_name))
        if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'current_shepard_profile_config.txt')):
            with open(os.path.join(os.path.dirname(os.path.realpath(__file__)), 'current_shepard_profile_config.txt'),'r') as config_file:
                current_profile = config_file.read().strip()
            if current_profile == profile_name:
                clear_profile_config()

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        raise ValueError(str(error))
    return
######################################################SET LIBRARIES STOP HERE######################################################

######################################################CLEAR PROFILE CONFIG LIBRARIES START HERE######################################################
def clear_profile_config():
    if os.path.exists(os.path.join(os.path.dirname(os.path.realpath(__file__)),'current_shepard_profile_config.txt')):
        try:
            os.remove(os.path.join(os.path.dirname(os.path.realpath(__file__)),'current_shepard_profile_config.txt'))
        except Exception as error:
            traceback.print_tb(error.__traceback__)
            raise ValueError(str(error))
        print('Profile config cleared!')
    else:
        print('No profile is currently set so there is no configuration to clear!')
    return
######################################################CLEAR PROFILE CONFIG LIBRARIES STOP HERE######################################################

######################################################WHERE AM I LIBRARIES START HERE######################################################
def where_am_i(directory_path):
    try:
        print('Here is the directory where your config files are located:')
        print(directory_path)
        print('You can drag profile files out of this directory to another directory specified by where_am_i on another machine to import profiles to another location.')
        print('Putting profiles in the path specified by this command will import them into your cli.')
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        raise ValueError(str(error))
    return
######################################################WHERE AM I LIBRARIES STOP HERE######################################################

######################################################RETRIEVE LIBRARIES START HERE######################################################
def retrieve(account_number,role_to_assume_to_target_account,s3_bucket_for_results,directory_to_sync_s3_bucket_to,dont_assume,mfa_token,serial_number):

    if not os.path.exists(directory_to_sync_s3_bucket_to):
        print(directory_to_sync_s3_bucket_to + ' is not a local directory that exists on your machine. Please supply a local directory that exists on your machine.')
        if not directory_to_sync_s3_bucket_to.endswith(os.path.sep):
            directory_to_sync_s3_bucket_to += os.path.sep
        return

    try:
        print('attempting to sync contents of s3 bucket named ' + s3_bucket_for_results + ' to the directory specified as ' + directory_to_sync_s3_bucket_to + '...')
        old_env = dict(os.environ)
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account

        activate_role_vars_if_exists()

        # where the programmatic s3 sync command happens
        ##################################################################################################################
        if dont_assume == 'False':

            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # SYNC DIRECTORIES USING AWSCLI
            print('Attempting to sync s3 bucket to local directory!')
            old_env = dict(os.environ)

            try:
                #SET NEW ENVRIONMENT
                env = os.environ.copy()
                env['LC_CTYPE'] = u'en_US.UTF'
                env['AWS_ACCESS_KEY_ID'] = newsession_id
                env['AWS_SECRET_ACCESS_KEY'] = newsession_key
                env['AWS_SESSION_TOKEN'] = newsession_token
                os.environ.update(env)

                # RUN COMMAND
                exit_code = create_clidriver().main(['s3', 'sync', 's3://'+s3_bucket_for_results, directory_to_sync_s3_bucket_to])
                if exit_code > 0:
                    raise RuntimeError('AWS CLI exited with code {}'.format(exit_code))

                #OLD ENVIRONMENT COMES BACK
                os.environ.clear()
                os.environ.update(old_env)
            except subprocess.CalledProcessError as error:
                os.environ.clear()
                os.environ.update(old_env)
                traceback.print_tb(error.__traceback__)
                print(error.output)
                raise ValueError(str(error))

            check_output('unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN',shell=True)
        else:
            exit_code = create_clidriver().main(['s3', 'sync', 's3://' + s3_bucket_for_results, directory_to_sync_s3_bucket_to])
            if exit_code > 0:
                raise RuntimeError('AWS CLI exited with code {}'.format(exit_code))
    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('attempt to sync contents of s3 bucket named ' + s3_bucket_for_results + ' to the directory specified as ' + directory_to_sync_s3_bucket_to + ' failed.')
        raise ValueError(str(error))
    print('attempt to sync contents of s3 bucket named ' + s3_bucket_for_results + ' to the directory specified as ' + directory_to_sync_s3_bucket_to + ' succeeded.')
######################################################RETRIEVE LIBRARIES STOP HERE######################################################

######################################################BATCH_VIA_API LIBRARIES START HERE######################################################
def batch_via_api(account_number,role_to_assume_to_target_account,lambda_to_invoke,json_payload,dont_assume,mfa_token,serial_number):
    print('attempting to invoke lambda named ' + lambda_to_invoke + '...')

    activate_role_vars_if_exists()

    try:
        region = check_output('aws configure get region', shell=True).strip().decode("utf-8")  # ONLY OHIO
        ACCOUNT_NUMBER = account_number
        IAM_ROLE = role_to_assume_to_target_account

        # where the programmatic cloudformation query happens
        ##################################################################################################################
        if dont_assume == 'False':
            boto_sts = boto3.client('sts')

            if mfa_token:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4()),
                    SerialNumber=serial_number,
                    TokenCode=mfa_token
                )
            else:
                print("RoleArn=" + 'arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE)
                stsresponse = boto_sts.assume_role(
                    RoleArn='arn:aws:iam::' + ACCOUNT_NUMBER + r':role/' + IAM_ROLE,
                    RoleSessionName=str(uuid.uuid4())
                )

            # Save the details from assumed role into vars
            newsession_id = stsresponse["Credentials"]["AccessKeyId"]
            newsession_key = stsresponse["Credentials"]["SecretAccessKey"]
            newsession_token = stsresponse["Credentials"]["SessionToken"]

            # Here I create a cloudformation client using the assumed creds.
            lambda_assumed_client = get_session(
                region,
                newsession_id,
                newsession_key,
                newsession_token
            ).client('lambda')
        else:
            # Here I create a cloudformation client using environment creds.
            lambda_assumed_client = boto3.session.Session(region_name=region).client('lambda')

        print('#####################################################################')
        print('#####################################################################')
        print('Attempting to evaluate the following string to json dictionary ...')
        print(str(json_payload))
        print("Hint: if this doesn't work sometimes you need to enclose everything within the json brackets in double quotes and the whole string in single quotes")
        print('I.E. make a call like this: shepard_cli % shepard_cli batch_via_api --json_payload '+"'{"+'"TAG":"HELLO"'+"}'")
        print('#####################################################################')
        print('#####################################################################')

        response = lambda_assumed_client.invoke(
                FunctionName=lambda_to_invoke,
                InvocationType='RequestResponse',
                LogType='Tail',
                Payload=json.dumps(json.loads(json_payload))
        )

        print(response)

    except Exception as error:
        traceback.print_tb(error.__traceback__)
        print('attempt to invoke lambda named ' + lambda_to_invoke + ' failed.')
        raise ValueError(str(error))
    print('attempt to invoke lambda named ' + lambda_to_invoke + ' succeeded. The response from the lambda client has been returned.')
    return response
######################################################BATCH_VIA_API LIBRARIES STOP HERE######################################################