"""Run: python3 -m unittest discover -s scripts/tests   (standard library only)."""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import follow_delivery as fd  # noqa: E402
from follow_delivery_core.calendar import window  # noqa: E402
from follow_delivery_core.contracts import upgrade_config  # noqa: E402

ME = 'dev@example.com'
# Wednesday 2026-11-04 03:00 UTC = 11:00 Singapore.
WED_11 = datetime(2026, 11, 4, 3, 0, tzinfo=timezone.utc)
CONFIG = {'schema_version': 2, 'profile': 'sample', 'timezone': 'Asia/Singapore', 'working_days': [0, 1, 2, 3, 4],
          'start': '10:00', 'end': '19:00', 'developer_identity': ME, 'allowlist': ['ABC-1', 'ABC-2'],
          'business_writes_enabled': True, 'objects': {'ABC-1': [{'source': 'dw', 'object_id': '42', 'owner': 'local'}]},
          'calendar_file': 'config/holidays.json'}
CALENDAR = {'years': {'2026': {'verified': True, 'dates': ['2026-11-09']}}}


class Sources:
    def __init__(self):
        self.jira = {t: {'updated': 'v1', 'status': 'Doing'} for t in CONFIG['allowlist']}
        self.dw = {'phase': 'running', 'v': 'a'}
        self.calls = 0
        self.fail = set()

    def readers(self):
        def jira(ticket, identity):
            self.calls += 1
            if ticket in self.fail: raise ValueError('jira_read_incomplete')
            j = self.jira[ticket]
            return {'ticket': ticket, 'source': 'jira', 'object_id': ticket, 'object_version': j['updated'], 'status': j['status'],
                    'issue_type': 'Task', 'summary': 's', 'developers': [ME], 'candidate_sha': None, 'pending_reason': None,
                    'evidence_refs': ['https://jira.example/' + ticket]}

        def obj(o, ticket):
            return {'ticket': ticket, 'source': 'dw', 'object_id': o['object_id'], 'object_version': self.dw['v'],
                    'status': self.dw['phase'], 'candidate_sha': None, 'pending_reason': None, 'evidence_refs': []}
        return {'jira': jira, 'object': obj}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.project = Path(self.tmp.name)
        (self.project / 'config').mkdir()
        self.write_config(CONFIG)
        (self.project / 'config/holidays.json').write_text(json.dumps(CALENDAR))
        self.src = Sources()

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, value):
        (self.project / 'config/followup.json').write_text(json.dumps(value))

    def call(self, *args, now=WED_11):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = fd.run(['--project', str(self.project), *args], now=now, readers=self.src.readers())
        result = json.loads(out.getvalue()); result['_exit'] = code
        return result

    def settle(self, now=WED_11):
        """A run that looks at every ticket and records where it stands."""
        t = self.call('tick', now=now)
        for item in t.get('tickets', []):
            self.call('claim', item['ticket'], '--owner', 'settle', now=now)
            self.call('checkpoint', item['ticket'], '--owner', 'settle', '--stage', 'coding', '--next', 'wait', now=now)
            self.call('release', item['ticket'], '--owner', 'settle', now=now)
        return t


class WindowTest(Base):
    def test_working_hours_weekends_holidays_and_unverified_years(self):
        years = CALENDAR['years']
        self.assertEqual(window(WED_11, years, CONFIG), 'allowed')
        self.assertEqual(window(WED_11.replace(hour=1, minute=59), years, CONFIG), 'outside_window')  # 09:59 SGT
        self.assertEqual(window(WED_11.replace(hour=11), years, CONFIG), 'outside_window')  # 19:00 SGT
        self.assertEqual(window(datetime(2026, 11, 7, 3, tzinfo=timezone.utc), years, CONFIG), 'weekend')
        self.assertEqual(window(datetime(2026, 11, 9, 3, tzinfo=timezone.utc), years, CONFIG), 'holiday')
        self.assertEqual(window(datetime(2027, 1, 5, 3, tzinfo=timezone.utc), years, CONFIG), 'calendar_not_covered')

    def test_outside_the_window_tick_reads_nothing(self):
        r = self.call('tick', now=WED_11.replace(hour=12))
        self.assertEqual((r['result'], r['reason']), ('idle', 'outside_window'))
        self.assertEqual(self.src.calls, 0)


class TickTest(Base):
    def test_first_run_reviews_everything_then_goes_idle_until_something_changes(self):
        first = self.settle()
        self.assertEqual(first['result'], 'work')
        self.assertEqual({t['ticket'] for t in first['tickets']}, {'ABC-1', 'ABC-2'})
        later = WED_11 + timedelta(minutes=30)
        self.assertEqual(self.call('tick', now=later)['reason'], 'no_change')
        self.src.dw = {'phase': 'completed', 'v': 'b'}
        changed = self.call('tick', now=later)
        self.assertEqual([t['ticket'] for t in changed['tickets']], ['ABC-1'])
        self.assertEqual(changed['tickets'][0]['why'], ['changed'])
        self.assertEqual(changed['tickets'][0]['events'][0]['was'], 'running')

    def test_daily_review_once_per_local_day(self):
        self.settle()
        self.assertEqual(self.call('tick', now=WED_11 + timedelta(hours=1))['result'], 'idle')
        nxt = self.call('tick', now=WED_11 + timedelta(days=1))
        self.assertEqual({tuple(t['why']) for t in nxt['tickets']}, {('daily_review',)})

    def test_check_due_wakes_a_ticket(self):
        self.settle()
        self.call('claim', 'ABC-2', '--owner', 'r1')
        self.call('checkpoint', 'ABC-2', '--owner', 'r1', '--stage', 'review', '--next', 'look again',
                  '--next-check-at', (WED_11 + timedelta(hours=2)).isoformat())
        self.call('release', 'ABC-2', '--owner', 'r1')
        self.assertEqual(self.call('tick', now=WED_11 + timedelta(hours=1))['result'], 'idle')
        due = self.call('tick', now=WED_11 + timedelta(hours=2, minutes=1))
        self.assertEqual([(t['ticket'], t['why']) for t in due['tickets']], [('ABC-2', ['check_due'])])

    def test_the_same_read_error_is_reported_once(self):
        self.settle()
        self.src.fail = {'ABC-2'}
        later = WED_11 + timedelta(minutes=30)
        self.assertEqual(self.call('tick', now=later)['result'], 'work')
        again = self.call('tick', now=later + timedelta(minutes=30))
        self.assertEqual(again['result'], 'idle')


class LedgerTest(Base):
    def begin(self, owner='r1', version='sha1', *extra, now=WED_11):
        return self.call('begin', '--owner', owner, '--ticket', 'ABC-1', '--kind', 'merge', '--target', 'mr:7', '--version', version, *extra, now=now)

    def test_a_write_needs_the_ticket_lock_the_window_and_the_switch(self):
        self.assertEqual(self.begin()['reason'], 'ticket_not_claimed')
        self.call('claim', 'ABC-1', '--owner', 'r1')
        self.assertEqual(self.begin(now=WED_11.replace(hour=11, minute=30))['reason'], 'outside_window:outside_window')
        self.write_config(dict(CONFIG, business_writes_enabled=False))
        self.assertEqual(self.begin()['reason'], 'writes_disabled')

    def test_done_write_is_never_redone_and_failed_needs_explicit_retry(self):
        self.call('claim', 'ABC-1', '--owner', 'r1')
        key = self.begin()['action']['action_key']
        self.assertEqual(self.call('end', key, '--owner', 'r1', '--status', 'done')['reason'], 'done_needs_readback_evidence')
        self.call('end', key, '--owner', 'r1', '--status', 'done', '--evidence', 'https://git/mr/7')
        self.assertEqual(self.begin()['status'], 'already_done')
        self.assertEqual(self.begin(version='sha2')['status'], 'started')

    def test_failed_then_retry_gets_a_new_attempt(self):
        self.call('claim', 'ABC-1', '--owner', 'r1')
        key = self.begin()['action']['action_key']
        self.call('end', key, '--owner', 'r1', '--status', 'failed', '--reason', 'pipeline red')
        self.assertEqual(self.begin()['status'], 'failed_before')
        retry = self.begin('r1', 'sha1', '--retry')
        self.assertEqual((retry['status'], retry['action']['attempt']), ('started', 2))

    def test_an_unconfirmed_write_blocks_new_writes_on_that_ticket(self):
        self.call('claim', 'ABC-1', '--owner', 'r1')
        key = self.begin()['action']['action_key']
        self.call('end', key, '--owner', 'r1', '--status', 'unknown', '--reason', 'timed out')
        self.assertTrue(self.begin(version='sha2')['reason'].startswith('reconcile_first'))
        self.assertEqual(self.call('release', 'ABC-1', '--owner', 'r1')['status'], 'kept')
        self.assertIn('unconfirmed_write', self.call('tick')['tickets'][0]['why'])


class CrashAndHandOverTest(Base):
    def test_a_crashed_run_is_reconciled_by_the_next_agent_before_it_takes_over(self):
        self.call('claim', 'ABC-1', '--owner', 'codex-run')
        key = self.call('begin', '--owner', 'codex-run', '--ticket', 'ABC-1', '--kind', 'deploy', '--target', 'test:svc')['action']['action_key']
        # codex-run dies here. Thirty-one minutes later another agent runs.
        later = WED_11 + timedelta(minutes=31)
        self.assertEqual(self.call('claim', 'ABC-1', '--owner', 'claude-run', now=WED_11 + timedelta(minutes=5))['status'], 'busy')
        blocked = self.call('claim', 'ABC-1', '--owner', 'claude-run', now=later)
        self.assertEqual((blocked['status'], blocked['open_actions']), ('reconcile_first', [key]))
        self.assertEqual(self.call('end', key, '--owner', 'claude-run', '--status', 'unknown', '--reason', 'x', now=later)['reason'],
                         'reconcile_needs_an_outcome')
        closed = self.call('end', key, '--owner', 'claude-run', '--status', 'done', '--evidence', 'deploy #9 ok', now=later)
        self.assertEqual(closed['reconciled_for'], 'codex-run')
        took = self.call('claim', 'ABC-1', '--owner', 'claude-run', now=later)
        self.assertEqual((took['status'], took['took_over_from'], took['generation']), ('acquired', 'codex-run', 2))

    def test_a_live_holders_write_cannot_be_closed_by_someone_else(self):
        self.call('claim', 'ABC-1', '--owner', 'a')
        key = self.call('begin', '--owner', 'a', '--ticket', 'ABC-1', '--kind', 'k', '--target', 't')['action']['action_key']
        self.assertEqual(self.call('end', key, '--owner', 'b', '--status', 'done', '--evidence', 'e')['reason'], 'held_by_its_owner')

    def test_checkpoint_is_the_hand_over_note(self):
        self.call('claim', 'ABC-1', '--owner', 'a')
        self.call('checkpoint', 'ABC-1', '--owner', 'a', '--stage', 'MR !7 in review', '--next', 'merge test after approval', '--note', 'reviewer: bob')
        self.call('release', 'ABC-1', '--owner', 'a')
        shown = self.call('show', 'ABC-1')
        self.assertEqual((shown['progress']['stage'], shown['progress']['by_owner'], shown['lock']), ('MR !7 in review', 'a', None))

    def test_writes_keep_the_lock_alive(self):
        self.call('claim', 'ABC-1', '--owner', 'a')
        t = WED_11 + timedelta(minutes=25)
        self.call('checkpoint', 'ABC-1', '--owner', 'a', '--stage', 's', '--next', 'n', now=t)
        self.assertEqual(self.call('claim', 'ABC-1', '--owner', 'b', now=t + timedelta(minutes=20))['status'], 'busy')


class MigrationTest(Base):
    def test_prototype_config_and_state_upgrade_in_place(self):
        v1 = dict({k: v for k, v in CONFIG.items()}, schema_version=1, scan_time='11:00', inspection_minutes=15, inspector_model='m1',
                  executor_model='m2', notification_target=None, scheduler_ids={'daily': 'x'})
        self.write_config(v1)
        state = self.project / 'state'; state.mkdir()
        db = sqlite3.connect(state / 'followup.sqlite3')
        db.executescript('CREATE TABLE tickets(ticket TEXT PRIMARY KEY,snapshot_json TEXT NOT NULL,checkpoint_json TEXT NOT NULL,updated_at TEXT NOT NULL);'
                         'CREATE TABLE events(event_key TEXT PRIMARY KEY,ticket TEXT NOT NULL,payload_json TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL);'
                         'CREATE TABLE actions(action_key TEXT PRIMARY KEY); CREATE TABLE leases(resource_key TEXT PRIMARY KEY);'
                         "INSERT INTO events VALUES('k','ABC-1','{}','pending','t'); PRAGMA user_version=1;")
        db.commit(); db.close()
        r = self.call('migrate')
        self.assertEqual((r['config_schema'], r['db_version'], r['writes_enabled']), (2, 2, True))
        self.assertEqual(set(json.loads((self.project / 'config/followup.json').read_text())), set(CONFIG))
        db = sqlite3.connect(state / 'followup.sqlite3')
        self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0], 1)
        self.assertIsNone(db.execute("SELECT name FROM sqlite_master WHERE name='actions'").fetchone())

    def test_unfinished_prototype_actions_stop_the_migration(self):
        state = self.project / 'state'; state.mkdir()
        db = sqlite3.connect(state / 'followup.sqlite3')
        db.executescript("CREATE TABLE actions(action_key TEXT); INSERT INTO actions VALUES('x'); PRAGMA user_version=1;"); db.commit(); db.close()
        r = self.call('show', 'ABC-1')
        self.assertEqual((r['_exit'], r['reason']), (2, 'prototype_actions_not_empty_reconcile_first'))

    def test_upgrade_keeps_scope_and_authority(self):
        v1 = dict(CONFIG, schema_version=1, scan_time='11:00', inspection_minutes=15, inspector_model='m', executor_model='m',
                  notification_target=None, scheduler_ids={})
        up = upgrade_config(v1)
        self.assertEqual((up['allowlist'], up['business_writes_enabled'], up['developer_identity']), (CONFIG['allowlist'], True, ME))


class ReaderTest(unittest.TestCase):
    def test_jira_snapshot_takes_developers_and_rejects_incomplete_reads(self):
        from follow_delivery_core.readers import jira_snapshot
        data = {'key': 'ABC-1', 'fields': {'status': {'name': 'Doing'}, 'issuetype': {'name': 'Task'}, 'updated': 'u1', 'summary': 's',
                                           'customfield_10307': {'emailAddress': ME}, 'customfield_27616': [{'name': 'other@example.com'}]}}
        fact = jira_snapshot(data, ME)
        self.assertEqual((fact['status'], fact['developers'], fact['object_version']), ('Doing', sorted([ME, 'other@example.com']), 'u1'))
        with self.assertRaises(ValueError):
            jira_snapshot({'key': 'ABC-1', 'fields': {}}, ME)


class WatchTest(Base):
    def test_watch_adds_one_observer_per_object(self):
        r = self.call('watch', 'ABC-2', '--source', 'dw', '--object-id', '77')
        self.assertEqual(r['status'], 'watching')
        self.assertEqual(self.call('watch', 'ABC-2', '--source', 'dw', '--object-id', '77')['status'], 'already_watched')
        self.assertEqual(self.call('watch', 'ZZZ-9', '--source', 'dw', '--object-id', '78')['reason'], 'ticket_not_allowlisted')


if __name__ == '__main__':
    unittest.main()
