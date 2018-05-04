import docker
from config import Config
import json
import time
import datetime
from bson.objectid import ObjectId

dockerClient = docker.DockerClient(base_url = 'unix://var/run/docker.sock', version = Config.DOCKER_VERSION)

from pymongo import MongoClient
client = MongoClient('localhost', 27017)
db = client.dagdb

def start_action(workflowId,action):
	restart=docker.types.RestartPolicy(condition='none', delay=0, max_attempts=0, window=0)
	bathpath='/nfs/'+workflowId+'/'
	savepath=bathpath+action['id']
	inputs=''
	for name in action['preActions']:
		inputs=inputs+bathpath+name+' '
	if not inputs:
		inputs=bathpath+'input'
	dockerClient.services.create(image=action['id'].lower(), 
		name=workflowId+'-'+action['id'],
		mounts=["nfs-volume:/nfs:rw"],
		command=action['script']+' '+savepath+' '+inputs,
		restart_policy=restart,
		labels={'task':'action',"workflowId":workflowId,"actionId":action['id']})

# data={
# 	"type":"",
# 	"workflowId":"",
# 	"actionId":"",
# 	"error":"",
# 	"executeTime":""
# }
def handle_action(data):
	workflowId = data['workflowId']
	workflow = db.workflows.find_one({'_id':ObjectId(workflowId)})
	if not workflow:
		return

	actionId=data['actionId']
	if data['error']:
		workflow['actions'][actionId]['state'] = 'error'
		workflow['actions'][actionId]['error'] = data['error']
		workflow['state'] = 'error'
		db.workflows.save(workflow)
		return


	workflow['actions'][actionId]['state'] = 'finnish'
	workflow['actions'][actionId]['executeTime'] = data['executeTime']
	workflow['finishNum']=workflow['finishNum']+1
	if workflow['finishNum'] == workflow['actionNum']:
		workflow['state']='finish'
		workflow['endTime']=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
		db.workflows.save(workflow)
		return

	if workflow['isStop']:
		workflow['state'] = 'stoped'
		workflow['actions'][actionId]['state'] = 'stoped'
		db.workflows.save(workflow)
		return

	nextActions = workflow['actions'][actionId]['nextActions']
	for nextActionName in nextActions:
		nextAction = workflow['actions'][nextActionName]
		waitNum = nextAction['waitNum']-1
		workflow['actions'][nextActionName]['waitNum'] = waitNum
		if waitNum == 0:
			start_action(workflowId,nextAction)
			workflow['actions'][nextActionName]['state'] = 'running'
	db.workflows.save(workflow)


def cycle():
	while(True):
		services = dockerClient.services.list(filters = {"label":"task"})
		for service in services:
			tasks = service.tasks()
			isFinish = True
			error = None
			for task in tasks:
				if task['DesiredState'] == 'running':
					isFinish = False
				if task['Status']['State'] == 'failed':
					error = task['Status']['Err']

			if isFinish:
				labels = service.attrs['Spec']['Labels']
				createTime = service.attrs['CreatedAt'][0:26]+'Z'
				createTime = datetime.datetime.strptime(createTime, '%Y-%m-%dT%H:%M:%S.%fZ')
				nowTime = datetime.datetime.utcnow()
				executeTime = (nowTime-createTime).total_seconds()
				data={
					"type": "action",
					"workflowId": labels['workflowId'],
					"actionId": labels['actionId'],
					"error": error,
					"executeTime": executeTime
				}
				print(data)
				handle_action(data)
				service.remove()
		time.sleep(1)

if __name__ == '__main__':
	cycle()

