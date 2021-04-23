#Arbitrary Worker Code by Jacob Mevorach

from __future__ import print_function
import time
import os
import subprocess
import boto3
import logging
from subprocess import check_output
import shutil
import json
import base64
import multiprocessing
import unicodedata
import re

#   ___       _     _ _                          _    _            _               _____           _
#  / _ \     | |   (_) |                        | |  | |          | |             /  __ \         | |
# / /_\ \_ __| |__  _| |_ _ __ __ _ _ __ _   _  | |  | | ___  _ __| | _____ _ __  | /  \/ ___   __| | ___
# |  _  | '__| '_ \| | __| '__/ _` | '__| | | | | |/\| |/ _ \| '__| |/ / _ \ '__| | |    / _ \ / _` |/ _ \
# | | | | |  | |_) | | |_| | | (_| | |  | |_| | \  /\  / (_) | |  |   <  __/ |    | \__/\ (_) | (_| |  __/
# \_| |_/_|  |_.__/|_|\__|_|  \__,_|_|   \__, |  \/  \/ \___/|_|  |_|\_\___|_|     \____/\___/ \__,_|\___|
#                                         __/ |
#                                        |___/

#from here (http://patorjk.com/software/taag/#p=display&f=Graffiti&t=Type%20Something%20)
#By Jacob Mevorach for Ginkgo Bioworks 2020
inputs_bucket = str(os.getenv('inputs_bucket')) #the triggers bucket
outputs_bucket = str(os.getenv('outputs_bucket')) #the bucket we'll upload results to
quick_deploy_bucket = str(os.getenv('quick_deploy_bucket')) #the bucket error logs get dumped to
table_name = str(os.getenv('table_name')) #the dynamo db that stores input commands and job metadatax
region = str(os.getenv('region')) #the region this is all in
INPUT_ZIP_NAME = str(os.getenv('INPUT_ZIP_NAME')) #name of the input zip file
USES_EFS = str(os.getenv('USES_EFS')) #True for uses, False for doesn't
USES_LUSTRE = str(os.getenv('USES_LUSTRE')) #True for uses, False for doesn't
SECRET_STORE = str(os.getenv('SECRET_STORE')) #the name of the secret store associated with this architecture.
ULIMIT_FILENO = str(os.getenv('ULIMIT_FILENO')) #the override for what we want our ulimit fileno to be.
IS_INVOKED = str(os.getenv('IS_INVOKED')) #whether or not the function was made by an api endpoint invocation or by an upload to an S3 bucket.
ALLOW_DOCKER_ACCESS = str(os.getenv('ALLOW_DOCKER_ACCESS')) #whether or not to allow access to the docker daemon to the underlying payload container.

def reconstitute_auths():
	# Create a Secrets Manager client
	session = boto3.session.Session(region_name=region)
	client = session.client(
		service_name='secretsmanager'
	)

	try:
		get_secret_value_response = client.get_secret_value(
			SecretId=SECRET_STORE
		)
	except ClientError as e:
		if e.response['Error']['Code'] == 'DecryptionFailureException':
			# Secrets Manager can't decrypt the protected secret text using the provided KMS key.
			# Deal with the exception here, and/or rethrow at your discretion.
			raise e
		elif e.response['Error']['Code'] == 'InternalServiceErrorException':
			# An error occurred on the server side.
			# Deal with the exception here, and/or rethrow at your discretion.
			raise e
		elif e.response['Error']['Code'] == 'InvalidParameterException':
			# You provided an invalid value for a parameter.
			# Deal with the exception here, and/or rethrow at your discretion.
			raise e
		elif e.response['Error']['Code'] == 'InvalidRequestException':
			# You provided a parameter value that is not valid for the current state of the resource.
			# Deal with the exception here, and/or rethrow at your discretion.
			raise e
		elif e.response['Error']['Code'] == 'ResourceNotFoundException':
			# We can't find the resource that you asked for.
			# Deal with the exception here, and/or rethrow at your discretion.
			raise e
	else:
		# change the JSON string into a JSON object
		jsonObject = json.loads(get_secret_value_response['SecretString'])
		for key in jsonObject:
			file = open(key, "wb+")  # append mode
			file.write(base64.b64decode(jsonObject[key].encode('utf8')))
			file.close()
	return

def upload_to_s3(file_name, bucket, object_name=None):

	client = boto3.session.Session(region_name=region).client('s3')

	# If S3 object_name was not specified, use file_name
	if object_name is None:
		object_name = file_name

	# Upload the file
	try:
		rv = check_output("aws s3 cp " + file_name + " s3://" + bucket + "/" + object_name, shell=True)
	except subprocess.CalledProcessError as e:
		output = e.output
		logging.log(level=logging.ERROR,msg=str(output))
		raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, output))
	return

def update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME = None):

	dynamodb_resource = boto3.session.Session(region_name=region).resource('dynamodb')

	timestr = time.strftime("%Y%m%d-%H%M%S")  # get timestring

	table = dynamodb_resource.Table(table_name)

	item = {}

	for k, v in item_blob.items():
		item[k] = v

	#These are the only three attributes that can actually change at any point
	item['START_TIME'] = START_TIME
	if END_TIME:
		item['END_TIME'] = END_TIME
	item['JOB_STATUS'] = JOB_STATUS

	with table.batch_writer() as batch:
		response = batch.put_item(
			Item=item
		)

	return 0

def find_job(table_name, region):

	dynamodb_resource = boto3.session.Session(region_name=region).resource('dynamodb')

	table = dynamodb_resource.Table(table_name)

	timestr = int(time.time())  # get timestring

	response = table.get_item(Key={'UUID': str(os.getenv('UUID'))})
	item = response['Item']
	if 'not_yet_initiated'.lower() == item['JOB_STATUS'].lower() and str(item['UUID']) == str(os.getenv('UUID')):
		update_item_in_dynamoDB(table_name, region, item, timestr, None, 'in_progress')
		return str(item['UUID']), item, timestr, None, 'in_progress'
	else:
		return False, False, False, False, False

if __name__ == "__main__":
	###################################################################################################################
	#search for job
	###################################################################################################################
	UUID, item_blob, START_TIME, END_TIME, JOB_STATUS = find_job(table_name, region)

	###################################################################################################################
	#if we couldn't find a job; then die.
	###################################################################################################################
	if not UUID:
		quit() #die if the request was malformed or non-existant.

	###################################################################################################################
	#begin main processing loop
	###################################################################################################################
	try:
		###################################################################################################################
		# get formatted start time variable
		###################################################################################################################
		START_TIME_TO_FORMAT = str(time.strftime("%Y%m%d-%H%M%S"))  # get timestring
		formatted_start_time = str(START_TIME_TO_FORMAT)[0:4] + '/' + str(START_TIME_TO_FORMAT)[4:6] + '/' + str(START_TIME_TO_FORMAT)[6:8] + '-' + str(
			START_TIME_TO_FORMAT)[9:11] + ':' + str(START_TIME_TO_FORMAT)[11:13] + ':' + str(START_TIME_TO_FORMAT)[13:15] + ' U.T.C.'

		###################################################################################################################
		# declare a location on the root file system on our container and make a directory name within it that will be unique.
		###################################################################################################################
		root_loc = r"/mnt/root"
		my_dir_root = "/mnt/root/" + str(UUID) #each call to our process gets assigned a unique UUID in the authoritative Dynamo DB table
		os.mkdir(my_dir_root)
		ROOT_INPUT_NAME = "/mnt/root/"+str(UUID)+"/input"
		os.mkdir(ROOT_INPUT_NAME)
		ROOT_OUTPUT_NAME = "/mnt/root/"+str(UUID)+"/output"
		os.mkdir(ROOT_OUTPUT_NAME)

		###################################################################################################################
		# parse quick deploy directory out if it exists as a variable
		###################################################################################################################
		if 'QUICK_DEPLOY_DIRECTORY' in [x.upper() for x in item_blob.keys()]:
			for k, v in item_blob.items():
				if k.upper() == 'QUICK_DEPLOY_DIRECTORY':
					QUICK_DEPLOY_DIRECTORY = v
		else:
			QUICK_DEPLOY_DIRECTORY = 'None'

		###################################################################################################################
		# declare the location of the efs mount on our container and make a directory name within it that will be unique if the user requests it.
		###################################################################################################################
		if USES_EFS == "True":
			efs_loc = r"/mnt/efs"
			efs_loc_read_only = r"/mnt/efs/read_only"
			my_dir_efs = "/mnt/efs/" + str(UUID) #each call to our process gets assigned a unique UUID in the authoritative Dynamo DB table
			os.mkdir(my_dir_efs)
			EFS_INPUT_NAME = "/mnt/efs/"+str(UUID)+"/input"
			os.mkdir(EFS_INPUT_NAME)
			EFS_OUTPUT_NAME = "/mnt/efs/"+str(UUID)+"/output"
			os.mkdir(EFS_OUTPUT_NAME)

		###################################################################################################################
		# declare the location of the lustre mount on our container and make a directory name within it that will be unique if the user requests it.
		###################################################################################################################
		if USES_LUSTRE == "True":
			lustre_loc = r"/mnt/fsx"
			lustre_loc_read_only = r"/mnt/fsx/read_only"
			my_dir_lustre = "/mnt/fsx/" + str(UUID) #each call to our process gets assigned a unique UUID in the authoritative Dynamo DB table
			os.mkdir(my_dir_lustre)
			LUSTRE_INPUT_NAME = "/mnt/fsx/"+str(UUID)+"/input"
			os.mkdir(LUSTRE_INPUT_NAME)
			LUSTRE_OUTPUT_NAME = "/mnt/fsx/"+str(UUID)+"/output"
			os.mkdir(LUSTRE_OUTPUT_NAME)

		###################################################################################################################
		# fetch job zip into inputs folder on root file system location or onto EFS or Lustre if either of those exist.
		###################################################################################################################
		if IS_INVOKED == "False":
			if USES_EFS == "True" or USES_LUSTRE == "True":
				if USES_EFS == "True":
					os.chdir(EFS_INPUT_NAME)
					rv = check_output("aws s3 cp s3://" + inputs_bucket + "/" + INPUT_ZIP_NAME + " " + INPUT_ZIP_NAME,
									  shell=True)
				if USES_LUSTRE == "True":
					os.chdir(LUSTRE_INPUT_NAME)
					rv = check_output("aws s3 cp s3://" + inputs_bucket + "/" + INPUT_ZIP_NAME + " " + INPUT_ZIP_NAME,
									  shell=True)
			else:
				os.chdir(ROOT_INPUT_NAME)
				rv = check_output("aws s3 cp s3://" + inputs_bucket + "/" + INPUT_ZIP_NAME + " " + INPUT_ZIP_NAME, shell=True)
		else:
			pass #this job was batched out via an API endpoint and thus doesn't have any variable to

		###################################################################################################################
		# fetch quick deploy inputs if requested from the user.
		###################################################################################################################
		if QUICK_DEPLOY_DIRECTORY != 'None':
			if USES_EFS == "True" or USES_LUSTRE == "True":
				if USES_EFS == "True":
					os.chdir(EFS_INPUT_NAME)
					os.mkdir(QUICK_DEPLOY_DIRECTORY)
					os.chdir(QUICK_DEPLOY_DIRECTORY)
					rv = check_output("aws s3 cp s3://" + quick_deploy_bucket + "/" + QUICK_DEPLOY_DIRECTORY + "/ ./ --recursive", shell=True)
				if USES_LUSTRE == "True":
					os.chdir(LUSTRE_INPUT_NAME)
					os.mkdir(QUICK_DEPLOY_DIRECTORY)
					os.chdir(QUICK_DEPLOY_DIRECTORY)
					rv = check_output("aws s3 cp s3://" + quick_deploy_bucket + "/" + QUICK_DEPLOY_DIRECTORY + "/ ./ --recursive", shell=True)
			else:
				os.chdir(ROOT_INPUT_NAME)
				os.mkdir(QUICK_DEPLOY_DIRECTORY)
				os.chdir(QUICK_DEPLOY_DIRECTORY)
				rv = check_output("aws s3 cp s3://" + quick_deploy_bucket + "/" + QUICK_DEPLOY_DIRECTORY + "/ ./ --recursive", shell=True)
		else:
			pass  # this job was batched out via an API endpoint and thus doesn't have any variable to


		###################################################################################################################
		# reconstitute any secret files here if they exist
		###################################################################################################################
		os.chdir(ROOT_INPUT_NAME)
		os.mkdir('secrets')
		os.chdir('secrets')
		reconstitute_auths()

		###################################################################################################################
		# update status to reflect you are now calling the project payload.
		###################################################################################################################
		JOB_STATUS = 'calling_payload_code ' + formatted_start_time
		update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
		logging.log(level=logging.INFO, msg=JOB_STATUS)

		###################################################################################################################
		# call payload
		###################################################################################################################
		os.chdir('/')

		#this action determines the environment variables available to the payload container.
		with open('environment_variables.env', 'w+') as the_file:
			for k, v in item_blob.items():
				if not str(k) == 'START_TIME' and not str(k) == 'JOB_STATUS':
					the_file.write(str(k)+'='+str(v)+'\n')
			the_file.write(str('START_TIME') + '=' + str(START_TIME) + '\n')
			the_file.write(str('JOB_STATUS') + '=' + str(JOB_STATUS) + '\n')
			the_file.write(str('INPUTS_BUCKET') + '=' + str(inputs_bucket) + '\n')
			the_file.write(str('OUTPUTS_BUCKET') + '=' + str(outputs_bucket) + '\n')
			the_file.write(str('QUICK_DEPLOY_BUCKET') + '=' + str(quick_deploy_bucket) + '\n')
			the_file.write(str('INPUT_ZIP_NAME') + '=' + str(INPUT_ZIP_NAME) + '\n')
			the_file.write(str('ROOT_INPUT_NAME') + '=' + str(ROOT_INPUT_NAME) + '\n')
			the_file.write(str('ROOT_OUTPUT_NAME') + '=' + str(ROOT_OUTPUT_NAME) + '\n')
			the_file.write(str('ALLOW_DOCKER_ACCESS') + '=' + str(ALLOW_DOCKER_ACCESS) + '\n')
			the_file.write(str('IS_INVOKED') + '=' + str(IS_INVOKED) + '\n')
			the_file.write(str('USES_EFS') + '=' + str(USES_EFS) + '\n')

			if USES_EFS == "True":
				the_file.write(str('EFS_INPUT_NAME') + '=' + str(EFS_INPUT_NAME) + '\n')
				the_file.write(str('EFS_OUTPUT_NAME') + '=' + str(EFS_OUTPUT_NAME) + '\n')
				the_file.write(str('EFS_READ_ONLY_PATH') + '=' + str(efs_loc_read_only) + '\n')

			the_file.write(str('USES_LUSTRE') + '=' + str(USES_LUSTRE) + '\n')
			if USES_LUSTRE == "True":
				the_file.write(str('LUSTRE_INPUT_NAME') + '=' + str(LUSTRE_INPUT_NAME) + '\n')
				the_file.write(str('LUSTRE_OUTPUT_NAME') + '=' + str(LUSTRE_OUTPUT_NAME) + '\n')
				the_file.write(str('LUSTRE_READ_ONLY_PATH') + '=' + str(lustre_loc_read_only) + '\n')

		call = 'docker load --input payload.tar'
		try:
			rv = check_output(call, shell=True)  ## FORMAT
		except subprocess.CalledProcessError as e:
			output = e.output
			logging.log(level=logging.ERROR,msg=str(output))
			raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, output))
			quit()

		#Pass the appropriate number of volume mounts!

		call = 'docker run --rm -a stdout -a stderr --name '+UUID+' --privileged=true' + ' --ulimit nofile='+ULIMIT_FILENO+':'+ULIMIT_FILENO

		#volume mount our root dir
		call = call + ' --volume ' + my_dir_root + ':' + my_dir_root + ' '  # allows write access to a single directory we manage

		# volume mount for docker daemon if requested
		if ALLOW_DOCKER_ACCESS == 'True':
			call = call + ' --volume ' + r"/var/run/docker.sock" + ':' + r"/var/run/docker.sock" + ' '  # allows write access to a single directory we manage

		#volume mount for efs dir if requested
		if USES_EFS == 'True':
			call = call + ' --volume ' + my_dir_efs + ':' + my_dir_efs + ' ' #allows write access to a single directory we manage
			call = call + ' --volume ' + efs_loc + ':' + efs_loc_read_only + ':' + 'ro' + ' ' #allows read only access to the whole thing

		#volume mount for lustre dir if requested
		if USES_LUSTRE == 'True':
			call = call + ' --volume ' + my_dir_lustre + ':' + my_dir_lustre + ' ' #allows write access to a single directory we manage
			call = call + ' --volume ' + lustre_loc + ':' + lustre_loc_read_only + ':' + 'ro' + ' ' #allows read only access to the whole thing

		#overwrite any local entrypoint and make it null so it gets ignored.
		if QUICK_DEPLOY_DIRECTORY != 'None':
			call = call + " --entrypoint=''" + ' '

		#add environment variables file and specify our image
		call = call + '--env-file environment_variables.env payload_image:latest'

		# specfiy a run.sh script
		if QUICK_DEPLOY_DIRECTORY != 'None':
			if USES_LUSTRE == "True":
				call = call + " chmod +x " + os.path.join(LUSTRE_INPUT_NAME, QUICK_DEPLOY_DIRECTORY,'run.sh') + ' && ' + os.path.join(LUSTRE_INPUT_NAME,QUICK_DEPLOY_DIRECTORY,'run.sh') + ' '
			else:
				if USES_EFS == "True":
					call = call + " chmod +x " + os.path.join(EFS_INPUT_NAME, QUICK_DEPLOY_DIRECTORY,'run.sh') + ' && ' + os.path.join(EFS_INPUT_NAME,QUICK_DEPLOY_DIRECTORY,'run.sh') + ' '
				else:
					call = call + " chmod +x " + os.path.join(ROOT_INPUT_NAME, QUICK_DEPLOY_DIRECTORY,'run.sh') + ' && ' + os.path.join(ROOT_INPUT_NAME,QUICK_DEPLOY_DIRECTORY,'run.sh') + ' '

		# make main call
		try:
			rv = check_output(call, shell=True)  ## FORMAT
		except subprocess.CalledProcessError as e:
			output = e.output
			logging.log(level=logging.ERROR,msg=str(output))
			raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, output))
			quit()

		###################################################################################################################
		# job was a success; pushing to s3
		###################################################################################################################
		JOB_STATUS = 'job_complete_pushing_to_s3'
		update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
		logging.log(level=logging.INFO, msg='job_complete_pushing_non_empty_results_directories_to_s3')

		os.chdir(my_dir_root)
		if os.listdir(ROOT_OUTPUT_NAME): #if directory is not empty we're doing an upload
			shutil.make_archive(my_dir_root + "/result", 'zip', ROOT_OUTPUT_NAME)
			if 'TAG' in [x.upper() for x in item_blob.keys()]:
				for k, v in item_blob.items():
					if k.lower() == 'tag':
						tag_to_append = v #so that our tag doesn't blow up by having weird characters in it
				link_to_results = upload_to_s3('result.zip', outputs_bucket, tag_to_append+'_result@' + UUID + '_' + str(START_TIME) + '_root' + '.zip')
			else:
				link_to_results = upload_to_s3('result.zip', outputs_bucket, 'result@' + UUID + '_' + str(START_TIME) + '_root' + '.zip')
			logging.log(level=logging.INFO, msg='root results directory uploaded to output s3 bucket')

		if USES_EFS == 'True':
			os.chdir(my_dir_efs)
			if os.listdir(EFS_OUTPUT_NAME): #if directory is not empty we're doing an upload
				shutil.make_archive(my_dir_efs + "/result", 'zip', EFS_OUTPUT_NAME)
				if 'TAG' in [x.upper() for x in item_blob.keys()]:
					for k, v in item_blob.items():
						if k.lower() == 'tag':
							tag_to_append = v #so that our tag doesn't blow up by having weird characters in it
					link_to_results = upload_to_s3('result.zip', outputs_bucket, tag_to_append+'_result@' + UUID + '_' + str(START_TIME) + '_efs' + '.zip')
				else:
					link_to_results = upload_to_s3('result.zip', outputs_bucket, 'result@' + UUID + '_' + str(START_TIME) + '_efs' + '.zip')
				logging.log(level=logging.INFO, msg='efs results directory uploaded to output s3 bucket')

		if USES_LUSTRE == 'True':
			os.chdir(my_dir_lustre)
			if os.listdir(LUSTRE_OUTPUT_NAME): #if directory is not empty we're doing an upload
				shutil.make_archive(my_dir_lustre + "/result", 'zip', LUSTRE_OUTPUT_NAME)
				if 'TAG' in [x.upper() for x in item_blob.keys()]:
					for k, v in item_blob.items():
						if k.lower() == 'tag':
							tag_to_append = v #so that our tag doesn't blow up by having weird characters in it
					link_to_results = upload_to_s3('result.zip', outputs_bucket, tag_to_append+'_result@' + UUID + '_' + str(START_TIME) + '_lustre' + '.zip')
				else:
					link_to_results = upload_to_s3('result.zip', outputs_bucket, 'result@' + UUID + '_' + str(START_TIME) + '_lustre' + '.zip')
				logging.log(level=logging.INFO, msg='efs results directory uploaded to output s3 bucket')

		###################################################################################################################
		# update status and clean workspace
		###################################################################################################################
		JOB_STATUS = 'job_complete_cleaning_up_workspace'
		update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
		logging.log(level=logging.INFO, msg='job_complete_cleaning_up_workspace')
		os.chdir(root_loc)
		rv = check_output('rm -rf ' + str(my_dir_root) + ' >/dev/null 2>&1', shell=True)  # kill your directory
		if USES_EFS == 'True':
			os.chdir(efs_loc)
			rv = check_output('rm -rf ' + str(my_dir_efs) + ' >/dev/null 2>&1', shell=True)  # kill your directory
		if USES_LUSTRE == 'True':
			os.chdir(lustre_loc)
			rv = check_output('rm -rf ' + str(my_dir_lustre) + ' >/dev/null 2>&1', shell=True)  # kill your directory

		###################################################################################################################
		# done
		###################################################################################################################
		END_TIME_TO_FORMAT = str(time.strftime("%Y%m%d-%H%M%S"))  # get timestring
		formatted_end_time = str(END_TIME_TO_FORMAT)[0:4] + '/' + str(END_TIME_TO_FORMAT)[4:6] + '/' + str(END_TIME_TO_FORMAT)[6:8] + '-' + str(
			END_TIME_TO_FORMAT)[9:11] + ':' + str(END_TIME_TO_FORMAT)[11:13] + ':' + str(END_TIME_TO_FORMAT)[13:15] + ' U.T.C.'
		JOB_STATUS = '<done>' + ' <' + str(formatted_end_time) + '>'
		END_TIME = int(time.time())
		update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
		logging.log(level=logging.INFO, msg='SUCCESS! JOB COMPLETE.')
		quit()

	except Exception as Error:
		try:
			###################################################################################################################
			# update status and clean workspace to minimize cost
			###################################################################################################################
			JOB_STATUS = 'job failed; cleaning up workspace'
			update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
			logging.log(level=logging.INFO, msg='job failed; cleaning up workspace')
			os.chdir(root_loc)
			rv = check_output('rm -rf ' + str(my_dir_root) + ' >/dev/null 2>&1', shell=True)  # kill your directory
			if USES_EFS == 'True':
				os.chdir(efs_loc)
				rv = check_output('rm -rf ' + str(my_dir_efs) + ' >/dev/null 2>&1', shell=True)  # kill your directory
			if USES_LUSTRE == 'True':
				os.chdir(lustre_loc)
				rv = check_output('rm -rf ' + str(my_dir_lustre) + ' >/dev/null 2>&1',shell=True)  # kill your directory

			###################################################################################################################
			# dead
			###################################################################################################################
			END_TIME_TO_FORMAT = str(time.strftime("%Y%m%d-%H%M%S"))  # get timestring
			formatted_end_time = str(END_TIME_TO_FORMAT)[0:4] + '/' + str(END_TIME_TO_FORMAT)[4:6] + '/' + str(
				END_TIME_TO_FORMAT)[6:8] + '-' + str(
				END_TIME_TO_FORMAT)[9:11] + ':' + str(END_TIME_TO_FORMAT)[11:13] + ':' + str(END_TIME_TO_FORMAT)[
																						 13:15] + ' U.T.C.'
			JOB_STATUS = '<done>' + ' <' + str(formatted_end_time) + '>'
			END_TIME = int(time.time())
			update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
			logging.log(level=logging.ERROR, msg=str(Error))

			###################################################################################################################
			# die. should kill instance.
			###################################################################################################################
			raise ValueError(str(Error))
			quit()
		except Exception as Error:
			###################################################################################################################
			# dead
			###################################################################################################################
			END_TIME_TO_FORMAT = str(time.strftime("%Y%m%d-%H%M%S"))  # get timestring
			formatted_end_time = str(END_TIME_TO_FORMAT)[0:4] + '/' + str(END_TIME_TO_FORMAT)[4:6] + '/' + str(
				END_TIME_TO_FORMAT)[6:8] + '-' + str(
				END_TIME_TO_FORMAT)[9:11] + ':' + str(END_TIME_TO_FORMAT)[11:13] + ':' + str(END_TIME_TO_FORMAT)[
																						 13:15] + ' U.T.C.'
			JOB_STATUS = '<done>' + ' <' + str(formatted_end_time) + '>'
			END_TIME = int(time.time())
			update_item_in_dynamoDB(table_name, region, item_blob, START_TIME, JOB_STATUS, END_TIME)
			logging.log(level=logging.ERROR, msg=str(Error))

			###################################################################################################################
			# die. should kill instance.
			###################################################################################################################
			raise ValueError(str(Error))
			quit()






