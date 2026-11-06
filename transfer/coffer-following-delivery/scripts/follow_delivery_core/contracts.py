import hashlib
import json
import re

TICKET = re.compile(r'^[A-Z][A-Z0-9]*-[1-9][0-9]*$')
MR_URL = re.compile(r'^https://git\.garena\.com/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)/-/merge_requests/([1-9][0-9]*)$')
PIPELINE_URL = re.compile(r'^https://git\.garena\.com/([A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+)/-/pipelines/([1-9][0-9]*)$')
HM = re.compile(r'^([01][0-9]|2[0-3]):[0-5][0-9]$')
SOURCES = ('dw', 'gitlab_mr', 'gitlab_pipeline')
FIELDS = {'schema_version', 'profile', 'timezone', 'working_days', 'start', 'end', 'developer_identity',
          'allowlist', 'business_writes_enabled', 'objects', 'calendar_file'}
# Fields of the first prototype that only served its Codex launcher and native schedule.
V1_ONLY = {'scan_time', 'inspection_minutes', 'inspector_model', 'executor_model', 'notification_target', 'scheduler_ids'}


def stable_key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


def eligible_issue(jira, config):
    return (bool(config['developer_identity']) and jira['ticket'] in config['allowlist']
            and config['developer_identity'] in jira['developers']
            and jira['issue_type'] in ('Task', 'Sub-task', 'Bug', 'Story')
            and jira['status'].lower() not in ('done', 'closed', 'cancelled', 'canceled'))


def event_allowed(event, config):
    fact = event['fact']; ticket = event['ticket']
    if ticket not in config['allowlist']: return False
    if fact['source'] == 'jira': return fact['object_id'] == ticket
    return any(o['source'] == fact['source'] and str(o['object_id']) == str(fact['object_id']) and o['owner'] == 'local'
               for o in config['objects'].get(ticket, []))


def validate_observer(obj):
    if set(obj) != {'source', 'object_id', 'owner'} or obj['source'] not in SOURCES or obj['owner'] not in ('local', 'dw'):
        raise ValueError('invalid_observer')
    ok = {'dw': lambda x: str(x).isdigit(), 'gitlab_mr': lambda x: bool(MR_URL.fullmatch(str(x))),
          'gitlab_pipeline': lambda x: bool(PIPELINE_URL.fullmatch(str(x)))}[obj['source']](obj['object_id'])
    if not ok: raise ValueError('invalid_object_id')


def upgrade_config(value):
    """Turn a schema 1 prototype config into schema 2 without changing scope or authority."""
    if value.get('schema_version') == 2: return value
    if value.get('schema_version') != 1: raise ValueError('unsupported_config_version')
    upgraded = {k: v for k, v in value.items() if k not in V1_ONLY}
    upgraded['schema_version'] = 2
    return validate_config(upgraded)


def validate_config(value):
    if set(value) != FIELDS: raise ValueError('configuration_fields')
    if value['schema_version'] != 2: raise ValueError('unsupported_config_version')
    if not isinstance(value['timezone'], str) or not value['timezone']: raise ValueError('invalid_timezone')
    days = value['working_days']
    if not isinstance(days, list) or not days or any(d not in range(7) for d in days): raise ValueError('invalid_working_days')
    if not all(isinstance(value[k], str) and HM.fullmatch(value[k]) for k in ('start', 'end')) or value['start'] >= value['end']:
        raise ValueError('invalid_working_hours')
    allow = value['allowlist']
    if not isinstance(allow, list) or any(not isinstance(t, str) or not TICKET.fullmatch(t) for t in allow) or len(set(allow)) != len(allow):
        raise ValueError('invalid_allowlist')
    ident = value['developer_identity']
    if ident is not None and (not isinstance(ident, str) or '@' not in ident): raise ValueError('invalid_developer_identity')
    if type(value['business_writes_enabled']) is not bool: raise ValueError('invalid_authority')
    if not isinstance(value['calendar_file'], str) or not value['calendar_file'].endswith('.json'):
        raise ValueError('invalid_calendar_reference')
    if not isinstance(value['objects'], dict) or set(value['objects']) - set(allow): raise ValueError('objects_outside_allowlist')
    seen = set()
    for objects in value['objects'].values():
        if not isinstance(objects, list): raise ValueError('invalid_objects')
        for obj in objects:
            validate_observer(obj)
            key = (obj['source'], str(obj['object_id']))
            if key in seen: raise ValueError('duplicate_observer')
            seen.add(key)
    return value
