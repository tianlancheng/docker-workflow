# -*- coding: utf-8 -*-
from flask import Blueprint,request
from flask import jsonify
from base import require_args,require_json
import re,json,os
from werkzeug import secure_filename
import datetime
from app import app,mongo
from bson.objectid import ObjectId
import tools
import shutil
import datetime

import docker
dockerClient=docker.DockerClient(base_url='unix://var/run/docker.sock', version=app.config['DOCKER_VERSION'])

dag = Blueprint('dag',__name__)

@dag.route('/template',methods=['POST'])
def add_template():
	data = json.loads(request.get_data())
	try:
		data=parse(data)
	except Exception,e:
		print(e)
		return jsonify(status=400, msg='parse error', data=None), 400
	id=mongo.db.templates.insert(data)
	res=mongo.db.templates.find_one({'_id':id})
	res['_id']=str(res['_id'])
	return jsonify(status=200, msg='success', data=res), 200

@dag.route('/templates',methods=['GET'])
@require_args('currentPage','pageSize')
def get_templates():
	currentPage=int(request.args.get("currentPage"))
	pageSize=int(request.args.get("pageSize"))
	skip=(currentPage-1)*pageSize
	filters=request.args.get('filters')
	if not filters:
		filters={}
	else:
		filters=json.loads(filters)
	results=mongo.db.templates.find(filters).sort("cteateTime",-1).skip(skip).limit(pageSize)
	data=[]
	for result in results:
		result['_id']=str(result['_id'])
		data.append(result)  
	return jsonify(status=200, msg='success', data=data), 200

@dag.route('/template/<id>',methods=['PUT'])
def update_template(id):
	data = json.loads(request.get_data())
	res=mongo.db.templates.find_one({'_id':ObjectId(id)},{'_id':1})
	if not res:
		return jsonify(status=400, msg='can not find template', data=None), 400
	mongo.db.templates.update({"_id":ObjectId(id)},{"$set":data})
	res=mongo.db.templates.find_one({'_id':ObjectId(id)})
	res['_id']=str(res['_id'])
	return jsonify(status=200, msg='success', data=res), 200

@dag.route('/template/<id>',methods=['DELETE'])
def delete_template(id):
	res=mongo.db.templates.find_one({'_id':ObjectId(id)},{'_id':1})
	if not res:
		return jsonify(status=400, msg='can not find template', data=None), 400
	mongo.db.templates.remove({'_id':ObjectId(id)})
	return jsonify(status=200, msg='success', data=None), 200

@dag.route('/workflow/start',methods=['POST'])
@require_args('templateId')
def start_workflow():
	templateId=request.args.get("templateId")
	try:
		file = request.files['file']
		filename=secure_filename(file.filename)
		print 'filename: '+filename
	except Exception,e:
		print(e)
		return jsonify(status=400, msg='no file upload', data=None), 400

	template=mongo.db.templates.find_one({'_id':ObjectId(templateId)})
	if not template:
		return jsonify(status=400, msg='can not find template', data=None), 400
	template['templateId']=str(template['_id'])
	del template['_id']
	
	id=mongo.db.workflows.insert(template)
	res=mongo.db.workflows.find_one({'_id':id})

	workflowId=str(res['_id'])
	savepath='/nfs-data/'+workflowId+'/input'
	tools.mkdir(savepath)
	file.save(os.path.join(savepath, filename))

	for k in res['actions']:
		action=res['actions'][k]
		if action['waitNum']==0:
			start_action(workflowId,action)
			res['actions'][k]['state']='running'
	res['startTime']=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
	mongo.db.workflows.save(res)
	res['_id']=str(res['_id'])
	return jsonify(status=200, msg='success', data=res), 200

@dag.route('/workflow/<id>/restart',methods=['POST'])
def restart_workflow(id):
	res=mongo.db.workflows.find_one({'_id':ObjectId(id)})
	if not res or res['state'] == 'running':
		return jsonify(status=400, msg='can not restart', data=None), 400
	template=mongo.db.templates.find_one({'_id':ObjectId(res['templateId'])},{'_id':0})
	if not template:
		return jsonify(status=400, msg='can not find template', data=None), 400
	mongo.db.workflows.update({"_id":ObjectId(id)},{"$set":template})
	res=mongo.db.workflows.find_one({'_id':ObjectId(id)})

	workflowId=str(res['_id'])
	for k in res['actions']:
		action=res['actions'][k]
		if action['waitNum']==0:
			start_action(workflowId,action)
			res['actions'][k]['state']='running'
	res['startTime']=datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S.%f')
	mongo.db.workflows.save(res)
	res['_id']=str(res['_id'])

	return jsonify(status=200, msg='success', data=res), 200

@dag.route('/workflows',methods=['GET'])
@require_args('currentPage','pageSize')
def get_workflows():
	currentPage=int(request.args.get("currentPage"))
	pageSize=int(request.args.get("pageSize"))
	skip=(currentPage-1)*pageSize
	filters=request.args.get('filters')
	if not filters:
		filters={}
	else:
		filters=json.loads(filters)
	results=mongo.db.workflows.find(filters).sort("cteateTime",-1).skip(skip).limit(pageSize)
	data=[]
	for result in results:
		result['_id']=str(result['_id'])
		data.append(result)  
	return jsonify(status=200, msg='success', data=data), 200

@dag.route('/workflow/<id>',methods=['GET'])
def get_workflow(id):
	res=mongo.db.workflows.find_one({'_id':ObjectId(id)})
	if not res:
		return jsonify(status=400, msg='can not find workflow', data=None), 400
	res['_id']=str(res['_id'])
	return jsonify(status=200, msg='success', data=res), 200


@dag.route('/workflow/<id>/stop',methods=['POST'])
def stop_workflow(id):
	res=mongo.db.workflows.find_one({'_id':ObjectId(id)},{'state':1})
	if not res or res['state'] != 'running':
		return jsonify(status=400, msg='can not stop', data=None), 400
	mongo.db.workflows.update({"_id":ObjectId(id)},{"$set":{"isStop":True}})
	return jsonify(status=200, msg='success', data=None), 200

@dag.route('/workflow/<id>',methods=['DELETE'])
def delete_workflow(id):
	path='/nfs-data/'+id
	if os.path.exists(path):
		shutil.rmtree(path)
	res=mongo.db.workflows.find_one({'_id':ObjectId(id)},{'_id':1})
	if res:
		mongo.db.workflows.remove({'_id':ObjectId(id)})	
	return jsonify(status=200, msg='success', data=None), 200



def start_action(workflowId,action):
	print("start action:"+workflowId+" "+action['id'])
	restart=docker.types.RestartPolicy(condition='none', delay=0, max_attempts=0, window=0)
	bathpath='/nfs/'+workflowId+'/'
	savepath=bathpath+action['id']
	inputs=''
	for name in action['preActions']:
		inputs=inputs+bathpath+name+' '
	if not inputs:
		inputs=bathpath+'input'
	dockerClient.services.create(image=action['componentId'].lower(), 
		name=workflowId+'-'+action['id'],
		mounts=["nfs-volume:/nfs:rw"],
		command=action['script']+' '+savepath+' '+inputs,
		restart_policy=restart,
		labels={'task':'action',"workflowId":workflowId,"actionId":action['id']})


def save_to_file(workflowName,recordDict):
	jsObj = json.dumps(recordDict)
	# name = os.path.basename(filepath)
	# path = os.path.dirname(filepath)
	# shotname,extension= os.path.splitext(name);
	fileObject = open(app.config['UPLOAD_FOLDER']+'/'+workflowName+'.json', 'w')  
	fileObject.write(jsObj)
	fileObject.close()

def get_namespace(element):
	m = re.match('\{.*\}', element.tag)
	return m.group(0) if m else ''
# {
# 	"_id":"",
# 	"isStop":False,
# 	"state":"",
# 	"totalNum":0,
# 	"finishNum":0,
# 	"startTime":"",
# 	"endTime":"",
# 	"actions":{
# 		"id":{
# 			"id":"actionA",
# 			"type":"action",
# 			"paramSetting":"",
# 			"script":"",
# 			"executeTime":"",
# 			"waitNum":0,
# 			"preActions":[],		
#           "nextActions":[],
# 			"state":None
# 			}
# 	},
# }
def parse(data):
	actions={}
	actionNum=0
	for node in data['nodes']:
		actionNum=actionNum+1
		action={
		"id": node['id'],
		"type": node['type'],
		"componentId": node['componentId'],
		"paramSetting": node['paramSetting'],
		"script": node['script'],
		"executeTime": None,
		"waitNum":0,
		"preActions":[],		
		"nextActions":[],
		"state":None
		}
		actions[node['id']]= action

	for edge in data['edges']:
		source= edge['source']
		target= edge['target']
		actions[source]['nextActions'].append(target)
		actions[target]['preActions'].append(source)
		actions[target]['waitNum']=actions[target]['waitNum']+1
	
	workflow= {
		"isStop": False,
		"state": "create",
		"actionNum": actionNum,
		"finishNum": 0,
		"startTime": None,
		"endTime": None,
		"actions":actions
	}	
	# print(workflow)
	#save_to_file(workflowName,workflow)
	return workflow