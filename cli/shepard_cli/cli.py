import shutil
import os
import boto3
import click
import uuid

from .lib import deploy,batch,query,describe,secretify,configure,check_for_updates,check_for_environment_variables,check_profile,set_profile,delete_profile,clear_profile_config,where_am_i,retrieve,check_role,set_role,release_role,batch_via_api,parse_inputs

version_number = 1.21

@click.command()
@click.argument("command", default='')
@click.option("--account_number", help="The number of the AWS account you want to act on should go here.", default=None)
@click.option("--use_env_variables", help="Even if you have a profile set you can set this flag to 'False' and the CLI will act as if you don't have a profile set allowing you to overwrite the profile variables you set.", default=None)
@click.option("--role_to_assume_to_target_account", help="This is the role you'd like to assume into in the target account to perform operations.", default=None)
@click.option("--path_to_docker_folder", help="Path to the folder on your local machine that contains a 'Dockerfile.txt' at minimum. The script will build your container using this folder.", default=None)
@click.option("--ecr_repo_to_push_to", help="The name of the ECR repo you'd like to push to should go here.", default=None)
@click.option("--path_to_local_folder_to_batch", help="Name of local folder you'd like to zip and push to the trigger bucket.", default=None)
@click.option("--s3_bucket_to_upload_to", help="The name of the trigger bucket you'd like to push to.", default=None)
@click.option("--dynamo_db_to_query", help="The name of the dynamoDB associated with an architecture you'd like to query.", default=None)
@click.option("--cloudformation_to_describe", help="This is the name of the cloudformation stack you'd like to describe.", default=None)
@click.option("--path_to_local_secrets", help="A path to a local folder of secrets files you'd like deployed to secrets manager.", default=None)
@click.option("--secret_store", help="The name of the secret manager store associated with your architecture goes here.", default=None)
@click.option("--profile_name", help="The name of the profile you'd like to act on goes here.", default=None)
@click.option("--zip_name_override", help="When you call the batch function and supply this argument you'll be able to specify a different zip name than the normal autogenerate UUID one it makes.", default=None)
@click.option("--s3_bucket_for_results", help="The name of the outputs bucket results get written to.", default=None)
@click.option("--directory_to_sync_s3_bucket_to", help="The path to the local directory you'd like to sync your s3 bucket to.", default=None)
@click.option("--dont_assume", help="Set this flag to True to not assume role to use a command. If you've set a role or your working in the root account this would make sense to do. Allowed values are "+'"'+"True"+'" or'+ ' "'+"False"+'".', default=None)
@click.option("--mfa_token", help="You can use this flag with any command that requires the 'role_to_assume_to_target_account' variables to provide an mfa token from an mfa device for use with assuming role.", default=None)
@click.option("--serial_number", help="Set this flag whenever you use set the mfa_token flag. This should be the ARN of the mfa device you're using to generate a token.", default=None)
@click.option("--lambda_to_invoke", help="Use this to describe a lambda for invoke calls to the api batching endpoint for an architecture.", default=None)
@click.option("--json_payload", help="A json filled with variables to send to the batching api endpoint.", default=None)
def run(command,account_number, use_env_variables, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, profile_name, zip_name_override, s3_bucket_for_results, directory_to_sync_s3_bucket_to, dont_assume, mfa_token, serial_number, lambda_to_invoke, json_payload):

    #Get initial context. This will be used for parsing inputs to functions just before their respective calls.
    initial_context = locals().copy()

    #set boolean flag defaults
    if use_env_variables is None:
        use_env_variables = 'True'
    if dont_assume is None:
        dont_assume = 'False'

    "Valid commands are: 'deploy','batch','batch_via_api','query','describe','secretify','update','configure','check_update','help','check_profile','clear_profile_config','set_profile','delete_profile','where_am_i','set_role','release_role', and 'check_role'."
    if not command:
        print()
        print("\033[4m" + 'GENERAL DESCRIPTION STARTS HERE' + "\033[0m")
        print('Welcome to Shepard CLI! Written 2020 by Jacob Mevorach for Ginkgo Bioworks.')
        print('Available commands: ' + "'deploy','batch','query','describe','secretify','update','configure','check_update','help','check_profile','clear_profile_config','set_profile','delete_profile','where_am_i','set_role','release_role','check_role'")
        print("\033[4m" + 'GENERAL DESCRIPTION ENDS HERE' + "\033[0m")
        print()
        print("\033[4m" + 'DESCRIPTION OF EACH COMMANDS ARGUMENTS STARTS HERE' + "\033[0m")
        print('deploy arguments: ' + "account_number,role_to_assume_to_target_account,path_to_docker_folder,ecr_repo_to_push_to")
        print('batch arguments: ' + "account_number,role_to_assume_to_target_account,path_to_local_folder_to_batch,s3_bucket_to_upload_to")
        print('query arguments: ' + "account_number,role_to_assume_to_target_account,dynamo_db_to_query")
        print('describe arguments: ' + "account_number,role_to_assume_to_target_account,cloudformation_to_describe")
        print('secretify arguments: ' + "account_number,role_to_assume_to_target_account,secret_store")
        print('retrieve arguments: ' + "account_number,role_to_assume_to_target_account,s3_bucket_for_results,directory_to_sync_s3_bucket_to")
        print('set_role arguments: ' + "account_number,role_to_assume_to_target_account,mfa_token,serial_number")
        print('batch_via_api arguments: ' + "account_number,role_to_assume_to_target_account,lambda_to_invoke,json_payload")
        print('configure arguments: ' + "profile_name")
        print('delete_profile arguments: ' + "profile_name")
        print('set_profile arguments: ' + "profile_name")
        print('clear_profile_config arguments: ' + "NONE!")
        print('check_profile arguments: ' + "NONE!")
        print('check_role arguments: ' + "NONE!")
        print('check_update arguments: ' + "NONE!")
        print('release_role arguments: ' + "NONE!")
        print('where_am_i arguments: ' + "NONE!")
        print("\033[4m" + 'DESCRIPTION OF EACH COMMANDS ARGUMENTS ENDS HERE' + "\033[0m")
        print()
        print("\033[4m" + 'OTHER OPTIONS START HERE' + "\033[0m")
        print('--use_env_variables: ' + "Even if you have a profile set you can set this flag to 'False' and the CLI will act as if you don't have a profile set allowing you to overwrite the profile variables you set. Only allowed when a function uses variables that could conceivably be set in a profile. If a function does not use any variables that can be set in a profile this flag does not apply and should not be used!")
        print('--mfa_token: ' + "You can use this flag with any command that requires the 'role_to_assume_to_target_account' variables to provide an mfa token from an mfa device for use with assuming role.")
        print('--serial_number: ' + "Set this flag whenever you use set the mfa_token flag. This should be the ARN of the mfa device you're using to generate a token.")
        print('--dont_assume: ' + "Set this flag to True to not assume role to use a command. Only applies to functions where a role can be assumed and does not apply and should not be used otherwise. If you've set a role or your working in the root account this would make sense to do. Allowed values are "+'"'+"True"+'" or'+ ' "'+"False"+'".')
        print("\033[4m" + 'OTHER OPTIONS END HERE' + "\033[0m")
        print()
        return

    command = str(command)

    if account_number != None:
        account_number = str(account_number)

    if role_to_assume_to_target_account != None:
        role_to_assume_to_target_account = str(role_to_assume_to_target_account)

    if path_to_docker_folder != None:
        path_to_docker_folder = str(path_to_docker_folder)

    if ecr_repo_to_push_to != None:
        ecr_repo_to_push_to = str(ecr_repo_to_push_to)

    if path_to_local_folder_to_batch != None:
        path_to_local_folder_to_batch = str(path_to_local_folder_to_batch)

    if s3_bucket_to_upload_to != None:
        s3_bucket_to_upload_to = str(s3_bucket_to_upload_to)

    if dynamo_db_to_query != None:
        dynamo_db_to_query = str(dynamo_db_to_query)

    if cloudformation_to_describe != None:
        cloudformation_to_describe = str(cloudformation_to_describe)

    if path_to_local_secrets != None:
        path_to_local_secrets = str(path_to_local_secrets)

    if secret_store != None:
        secret_store = str(secret_store)

    if s3_bucket_for_results != None:
        s3_bucket_for_results = str(s3_bucket_for_results)

    if directory_to_sync_s3_bucket_to != None:
        directory_to_sync_s3_bucket_to = str(directory_to_sync_s3_bucket_to)

    if lambda_to_invoke != None:
        lambda_to_invoke = str(lambda_to_invoke)

    if json_payload != None:
        json_payload = str(json_payload)

    os.chdir(os.path.dirname(os.path.realpath(__file__)))

    if os.path.exists('temp_store'):
        shutil.rmtree('temp_store')
        os.mkdir('temp_store')
    else:
        os.mkdir('temp_store')

    os.chdir(os.path.join(os.path.dirname(os.path.realpath(__file__)),'temp_store'))

    if use_env_variables not in ['True','False']:
        print('"'+use_env_variables+'"'+ ' was not recognized as a valid option for the "use_env_variables" flag. Valid options are: ' + "'True' or 'False'" +".")
        raise ValueError('Invalid environment variables flag supplied!')

    if dont_assume not in ['True','False']:
        print('"'+dont_assume+'"'+ ' was not recognized as a valid option for the "dont_assume" flag. Valid options are: ' + "'True' or 'False'" +".")
        raise ValueError('Invalid environment variables flag supplied!')

    if command not in ['deploy','batch','batch_via_api','query','describe','secretify','update','configure','check_update','help','check_profile','clear_profile_config','set_profile','delete_profile','where_am_i','retrieve','set_role','release_role','check_role']:
        print('"'+command+'"'+ ' was not recognized as a valid command. Valid commands are: ' + "'deploy','batch','batch_via_api','query','describe','secretify','check_update','configure','check_profile','clear_profile_config','delete_profile','where_am_i','retrieve','set_role','check_role','release_role' and 'set_profile'.")
        raise ValueError('Invalid command supplied!')

    if dont_assume == 'True':
        role_to_assume_to_target_account = str(uuid.uuid4())  # make the argument a random string if you're not assuming so we don't trigger the non initialization check if no default is set.
        account_number = str(uuid.uuid4())  # make the argument a random string if you're not assuming so we don't trigger the non initialization check if no default is set.

    if use_env_variables == 'True':
        if command not in ['clear_profile_config', 'check_profile','check_role','check_update', 'release_role', 'where_am_i']:
            account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to, dynamo_db_to_query, cloudformation_to_describe, path_to_local_secrets, secret_store, s3_bucket_for_results, directory_to_sync_s3_bucket_to, lambda_to_invoke = check_for_environment_variables(account_number, role_to_assume_to_target_account, path_to_docker_folder, ecr_repo_to_push_to, path_to_local_folder_to_batch, s3_bucket_to_upload_to,dynamo_db_to_query,cloudformation_to_describe,path_to_local_secrets,secret_store,s3_bucket_for_results,directory_to_sync_s3_bucket_to,lambda_to_invoke)

    if command == 'deploy':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_docker_folder','ecr_repo_to_push_to']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_docker_folder','ecr_repo_to_push_to','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        deploy(account_number,role_to_assume_to_target_account,path_to_docker_folder,ecr_repo_to_push_to,dont_assume,mfa_token,serial_number)

    if command == 'batch':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_local_folder_to_batch','s3_bucket_to_upload_to']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_local_folder_to_batch','s3_bucket_to_upload_to','zip_name_override','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        #zip_name_override is not checked for initialization because it's an optional argument
        batch(account_number,role_to_assume_to_target_account,path_to_local_folder_to_batch,s3_bucket_to_upload_to,zip_name_override,dont_assume,mfa_token,serial_number)

    if command == 'query':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','dynamo_db_to_query']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','dynamo_db_to_query','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        query(account_number,role_to_assume_to_target_account,dynamo_db_to_query,dont_assume,mfa_token,serial_number)

    if command == 'describe':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','cloudformation_to_describe']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','cloudformation_to_describe','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        describe(account_number,role_to_assume_to_target_account,cloudformation_to_describe,dont_assume,mfa_token,serial_number)

    if command == 'secretify':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_local_secrets','secret_store']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','path_to_local_secrets','secret_store','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        secretify(account_number,role_to_assume_to_target_account,path_to_local_secrets,secret_store,dont_assume,mfa_token,serial_number)

    if command == 'configure':

        minimum_variables_to_be_declared = ['profile_name']
        maximum_variables_to_be_declared = ['profile_name']
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        configure(profile_name)

    if command == 'set_profile':

        minimum_variables_to_be_declared = ['profile_name']
        maximum_variables_to_be_declared = ['profile_name']
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        set_profile(profile_name)

    if command == 'delete_profile':

        minimum_variables_to_be_declared = ['profile_name']
        maximum_variables_to_be_declared = ['profile_name']
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        delete_profile(profile_name)

    if command == 'check_profile':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        check_profile()

    if command == 'clear_profile_config':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        clear_profile_config()

    if command == 'where_am_i':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        where_am_i(os.path.join(os.path.dirname(os.path.realpath(__file__))))

    if command == 'retrieve':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','s3_bucket_for_results','directory_to_sync_s3_bucket_to']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','s3_bucket_for_results','directory_to_sync_s3_bucket_to','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        retrieve(account_number,role_to_assume_to_target_account,s3_bucket_for_results,directory_to_sync_s3_bucket_to,dont_assume,mfa_token,serial_number)

    if command == 'check_update':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        try:
            check_for_updates()
        except:
            print(
                'Could not check for updates because https://github.com/ginkgobioworks/shepard was unreachable or because command line credentials to access https://github.com/ginkgobioworks/shepard were not configured.')
            raise ValueError(
                'Could not check for updates because https://github.com/ginkgobioworks/shepard was unreachable or because command line credentials to access https://github.com/ginkgobioworks/shepard were not configured.')

    if command == 'set_role':

        minimum_variables_to_be_declared = ['account_number', 'role_to_assume_to_target_account']
        maximum_variables_to_be_declared = ['account_number', 'role_to_assume_to_target_account', 'mfa_token', 'serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        set_role(account_number, role_to_assume_to_target_account, mfa_token, serial_number)

    if command == 'check_role':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        check_role()

    if command == 'release_role':

        minimum_variables_to_be_declared = []
        maximum_variables_to_be_declared = []
        variables_exempt_from_parsing = []

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        release_role()

    if command == 'batch_via_api':

        minimum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','lambda_to_invoke','json_payload']
        maximum_variables_to_be_declared = ['account_number','role_to_assume_to_target_account','lambda_to_invoke','json_payload','dont_assume','mfa_token','serial_number']
        variables_exempt_from_parsing = ['use_env_variables']

        parse_inputs(command, minimum_variables_to_be_declared, maximum_variables_to_be_declared,
                     variables_exempt_from_parsing, initial_context, locals().copy())

        batch_via_api(account_number,role_to_assume_to_target_account,lambda_to_invoke,json_payload,dont_assume,mfa_token,serial_number)

    if command == 'help':
        print()
        print("\033[4m" + 'GENERAL DESCRIPTION STARTS HERE' + "\033[0m")
        print('Welcome to Shepard CLI! Written 2020 by Jacob Mevorach for Ginkgo Bioworks.')
        print('Available commands: ' + "'deploy','batch','batch_via_api','query','describe','secretify','update','configure','check_update','help','check_profile','set_profile','delete_profile','where_am_i','set_role','release_role','check_role'")
        print("\033[4m" + 'GENERAL DESCRIPTION ENDS HERE' + "\033[0m")
        print()
        print("\033[4m" + 'DESCRIPTION OF EACH COMMANDS ARGUMENTS STARTS HERE' + "\033[0m")
        print('deploy arguments: ' + "account_number,role_to_assume_to_target_account,path_to_docker_folder,ecr_repo_to_push_to")
        print('batch arguments: ' + "account_number,role_to_assume_to_target_account,path_to_local_folder_to_batch,s3_bucket_to_upload_to")
        print('query arguments: ' + "account_number,role_to_assume_to_target_account,dynamo_db_to_query")
        print('describe arguments: ' + "account_number,role_to_assume_to_target_account,cloudformation_to_describe")
        print('secretify arguments: ' + "account_number,role_to_assume_to_target_account,secret_store")
        print('retrieve arguments: ' + "account_number,role_to_assume_to_target_account,s3_bucket_for_results,directory_to_sync_s3_bucket_to")
        print('set_role arguments: ' + "account_number,role_to_assume_to_target_account,mfa_token,serial_number")
        print('batch_via_api arguments: ' + "account_number,role_to_assume_to_target_account,lambda_to_invoke,json_payload")
        print('configure arguments: ' + "profile_name")
        print('delete_profile arguments: ' + "profile_name")
        print('set_profile arguments: ' + "profile_name")
        print('clear_profile_config arguments: ' + "NONE!")
        print('check_profile arguments: ' + "NONE!")
        print('check_role arguments: ' + "NONE!")
        print('check_update arguments: ' + "NONE!")
        print('release_role arguments: ' + "NONE!")
        print('where_am_i arguments: ' + "NONE!")
        print("\033[4m" + 'DESCRIPTION OF EACH COMMANDS ARGUMENTS ENDS HERE' + "\033[0m")
        print()
        print("\033[4m" + 'OTHER OPTIONS START HERE' + "\033[0m")
        print('--use_env_variables: ' + "Even if you have a profile set you can set this flag to 'False' and the CLI will act as if you don't have a profile set allowing you to overwrite the profile variables you set. Only allowed when a function uses variables that could conceivably be set in a profile. If a function does not use any variables that can be set in a profile this flag does not apply and should not be used!")
        print('--mfa_token: ' + "You can use this flag with any command that requires the 'role_to_assume_to_target_account' variables to provide an mfa token from an mfa device for use with assuming role.")
        print('--serial_number: ' + "Set this flag whenever you use set the mfa_token flag. This should be the ARN of the mfa device you're using to generate a token.")
        print('--dont_assume: ' + "Set this flag to True to not assume role to use a command. Only applies to functions where a role can be assumed and does not apply and should not be used otherwise. If you've set a role or your working in the root account this would make sense to do. Allowed values are "+'"'+"True"+'" or'+ ' "'+"False"+'".')
        print("\033[4m" + 'OTHER OPTIONS END HERE' + "\033[0m")
        print()


