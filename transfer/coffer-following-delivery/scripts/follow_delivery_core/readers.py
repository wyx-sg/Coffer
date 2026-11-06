"""Read-only source readers for the shopee-account profile (Jira, DW, GitLab via skynet-base)."""
import json
import subprocess
import tempfile
import re
from pathlib import Path
from .contracts import stable_key, MR_URL, PIPELINE_URL


def call_json(argv, timeout=40, allow_array=False):
    try:
        result=subprocess.run(argv,capture_output=True,text=True,timeout=timeout,shell=False)
        if result.returncode: raise ValueError('reader_exit_'+str(result.returncode))
        value=json.loads(result.stdout)
        if allow_array and isinstance(value,list): return value
        if not isinstance(value,dict) or value.get('isError') or value.get('error') or value.get('errorMessages'):
            raise ValueError('reader_business_error')
        return value
    except (subprocess.TimeoutExpired,json.JSONDecodeError,OSError) as error:
        raise ValueError(type(error).__name__) from None


def jira_snapshot(data, identity):
    fields=data.get('fields',data)
    key=data.get('key') or data.get('issueKey')
    if not key or data.get('errorMessages') or not fields.get('status'): raise ValueError('jira_read_incomplete')
    custom=fields.get('customFields',fields)
    people=[]
    for value in [custom.get('customfield_10307'),*(custom.get('customfield_27616') or [])]:
        if isinstance(value,dict):
            name=value.get('emailAddress') or value.get('name')
            if name: people.append(name)
    status=fields['status']; kind=fields.get('issuetype',fields.get('issueType'))
    return {'ticket':key,'source':'jira','object_id':key,'object_version':fields.get('updated') or stable_key({'status':status,'developers':people}),'status':status.get('name') if isinstance(status,dict) else status,'issue_type':kind.get('name') if isinstance(kind,dict) else kind,'summary':fields.get('summary',''),'developers':sorted(set(people)),'candidate_sha':None,'pending_reason':None,'evidence_refs':[data.get('issueUrl') or 'https://jira.shopee.io/browse/'+key]}


def dw_snapshot(data,ticket):
    if not data.get('task_id') or data.get('phase') not in ('waiting','starting','running','pending','completed','cancel','failed'):
        raise ValueError('dw_read_incomplete')
    relevant={k:data.get(k) for k in ('task_id','phase','pending_reason','current_agent_id','finished_at','files','repos')}
    return {'ticket':ticket,'source':'dw','object_id':data['task_id'],'object_version':stable_key(relevant),'status':data['phase'],'candidate_sha':None,'pending_reason':data.get('pending_reason'),'evidence_refs':[data['url']] if data.get('url') else []}


def read_jira(ticket,identity):
    fact=jira_snapshot(call_json(['skynet-base','jira','read',ticket,'--fields','summary,status,issuetype,updated,customfield_10307,customfield_27616','--json']),identity)
    if fact['object_id']!=ticket: raise ValueError('jira_identity_mismatch')
    return fact


def _dw_helper():
    # Sibling skill in the same skill library; resolve() follows the agent's link to the master folder.
    here=Path(__file__).resolve()
    helper=here.parents[3]/'shopee-digital-worker/scripts/platform_mcp.py'
    if not helper.is_file(): raise ValueError('dw_helper_missing')
    return helper


def read_dw(task,ticket,tmp_dir):
    tmp_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',suffix='.json',dir=tmp_dir) as params:
        json.dump({'task_id':task},params); params.flush()
        fact=dw_snapshot(call_json(['python3',str(_dw_helper()),'call','task_get','--args-file',params.name]),ticket)
        if str(fact['object_id'])!=str(task): raise ValueError('dw_identity_mismatch')
        return fact


def mr_snapshot(data,sha,ticket,url):
    match=MR_URL.fullmatch(url)
    if not match or str(data.get('iid'))!=match[2] or data.get('webUrl')!=url or not re.fullmatch(r'[0-9a-f]{40,64}',sha):
        raise ValueError('mr_identity_or_sha_incomplete')
    meta={k:data.get(k) for k in ('state','updatedAt','draft','hasConflicts','reviewers')}
    meta['sha']=sha
    return {'ticket':ticket,'source':'gitlab_mr','object_id':url,'object_version':stable_key(meta),'status':data['state'],'candidate_sha':sha,'pending_reason':None,'evidence_refs':[url]}


def pipeline_snapshot(data,ticket,url):
    match=PIPELINE_URL.fullmatch(url)
    if not match or str(data.get('id'))!=match[2] or not data.get('status'):
        raise ValueError('pipeline_identity_incomplete')
    meta={k:data.get(k) for k in ('id','status','sha','jobs')}
    return {'ticket':ticket,'source':'gitlab_pipeline','object_id':url,'object_version':stable_key(meta),'status':data['status'],'candidate_sha':data.get('sha'),'pending_reason':None,'evidence_refs':[url]}


def read_object(obj,ticket,tmp_dir):
    if obj['source']=='dw': return read_dw(str(obj['object_id']),ticket,tmp_dir)
    url=str(obj['object_id'])
    if obj['source']=='gitlab_mr':
        match=MR_URL.fullmatch(url)
        if not match: raise ValueError('invalid_mr_ref')
        mr=call_json(['skynet-base','gitlab','mr','read',url])
        branch=mr.get('sourceBranch')
        if not branch: raise ValueError('missing_source_branch')
        branches=call_json(['skynet-base','gitlab','branch','list','--project',match[1],'--search',branch,'--limit','20'],allow_array=True)
        exact=[b for b in branches if b.get('name')==branch] if isinstance(branches,list) else []
        if len(exact)!=1 or not exact[0].get('commitShortId'): raise ValueError('branch_not_resolved')
        commit=call_json(['skynet-base','gitlab','commit','read',exact[0]['commitShortId'],'--project',match[1]])
        return mr_snapshot(mr,commit.get('id',''),ticket,url)
    if obj['source']=='gitlab_pipeline':
        if not PIPELINE_URL.fullmatch(url): raise ValueError('invalid_pipeline_ref')
        return pipeline_snapshot(call_json(['skynet-base','gitlab','pipeline','read',url]),ticket,url)
    raise ValueError('observer_carrier_unavailable')
