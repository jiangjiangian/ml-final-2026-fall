"""Exercise the hosted shell entrypoint without networking or running a stage."""

import json
import os
from datetime import datetime
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest


PROJECT = Path(__file__).resolve().parents[1]
WRAPPER = PROJECT / 'deployment/hosted/run.sh'
WORKFLOW = PROJECT.parent / '.github/workflows/financial-daily.yml'

# The fake executable records shell arguments. For manual auto only, it runs the
# real selector snippet with a fixed runner clock, never the networked CLI.
FAKE_PYTHON = '''import json
import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

capture = Path(os.environ['SCHEDULE_TEST_CAPTURE'])
with capture.open('a') as stream:
    stream.write(json.dumps(sys.argv[1:]) + '\\n')
if sys.argv[1:] == ['-']:
    if os.environ.get('SCHEDULE_TEST_FORBID_AUTO') == 'true':
        raise SystemExit('scheduled job must not reselect a stage from its start time')
    fixed = datetime.fromisoformat(os.environ['SCHEDULE_TEST_NOW'])
    class RunnerDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz is not None else fixed.replace(tzinfo=None)
    with patch('datetime.datetime', RunnerDatetime):
        exec(sys.stdin.read(), {'__name__': '__main__'})
'''


class ScheduleDispatchTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        binary = self.base / 'python'
        binary.write_text('#!' + sys.executable + '\n' + FAKE_PYTHON)
        binary.chmod(0o700)
        self.capture = self.base / 'arguments.jsonl'
        self.environment = {key: value for key, value in os.environ.items()
                            if not key.startswith(('FINPRED_', 'COURSE_', 'GITHUB_', 'SCHEDULE_TEST_'))}
        self.environment.update({
            'PATH': str(self.base) + os.pathsep + os.environ.get('PATH', ''),
            'FINPRED_DATA_ROOT': str(self.base / 'data'),
            'FINPRED_DATA_REPOSITORY': 'team/financial-model',
            'FINPRED_MODE': 'financial',
            'FINPRED_EVENT_NAME': 'schedule',
            'FINPRED_STAGE': 'auto',
            'SCHEDULE_TEST_CAPTURE': str(self.capture),
            'SCHEDULE_TEST_NOW': '2026-11-03T00:21:00+00:00',
            'SCHEDULE_TEST_FORBID_AUTO': 'true',
        })

    def run_wrapper(self, **environment):
        self.capture.unlink(missing_ok=True)
        result = subprocess.run(['bash', str(WRAPPER)], cwd=PROJECT,
                                env={**self.environment, **environment},
                                capture_output=True, text=True, timeout=15)
        calls = [json.loads(line) for line in self.capture.read_text().splitlines()] if self.capture.exists() else []
        return result, calls

    def test_every_declared_cron_keeps_its_intended_stage(self):
        schedules = re.findall(r"^\s+- cron: '([^']+)'", WORKFLOW.read_text(), re.MULTILINE)
        self.assertEqual(len(schedules), 4, 'each operation needs its own identifiable schedule event')
        for schedule, expected in zip(schedules, ('train', 'predict', 'submit', 'verify')):
            with self.subTest(schedule=schedule):
                result, calls = self.run_wrapper(FINPRED_SCHEDULE=schedule)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(len(calls), 1, 'schedule must not run the clock-based auto selector')
                arguments = calls[0]
                self.assertEqual(arguments[0], 'scripts/run_hosted_pipeline.py')
                self.assertEqual(arguments[arguments.index('--mode') + 1], 'stage')
                self.assertEqual(arguments[arguments.index('--stage') + 1], expected)

    def test_0810_prediction_delayed_until_0821_stays_prediction(self):
        result, calls = self.run_wrapper(FINPRED_SCHEDULE='10 0 * * *', FINPRED_STAGE='submit')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index('--stage') + 1], 'predict')
        self.assertNotIn('--submit', calls[0])

    def test_unknown_or_missing_schedule_stops_before_python(self):
        for schedule in ('', '10,20,35 0 * * *', '0 0 * * *'):
            with self.subTest(schedule=schedule):
                result, calls = self.run_wrapper(FINPRED_SCHEDULE=schedule, FINPRED_STAGE='predict')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Unknown financial schedule', result.stderr)
                self.assertEqual(calls, [])

    def test_manual_auto_retains_real_clock_selector(self):
        for now, expected in (('2026-11-02T23:25:00+00:00', 'train'),
                              ('2026-11-03T00:15:00+00:00', 'predict'),
                              ('2026-11-03T00:21:00+00:00', 'submit'),
                              ('2026-11-03T00:45:00+00:00', 'verify')):
            with self.subTest(now=now):
                result, calls = self.run_wrapper(FINPRED_EVENT_NAME='workflow_dispatch',
                                                FINPRED_SCHEDULE='unknown',
                                                SCHEDULE_TEST_FORBID_AUTO='false', SCHEDULE_TEST_NOW=now)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls[0], ['-'])
                self.assertEqual(calls[1][calls[1].index('--stage') + 1], expected)

    def test_manual_auto_after_deadline_stops_before_stage(self):
        result, calls = self.run_wrapper(FINPRED_EVENT_NAME='workflow_dispatch',
                                        SCHEDULE_TEST_FORBID_AUTO='false',
                                        SCHEDULE_TEST_NOW='2026-11-03T01:00:00+00:00')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, [['-']])

    def test_late_scheduled_stage_still_hits_the_real_daily_deadline_guard(self):
        from finpred.pipelines.daily import PipelineBlocked, run_stage

        result, calls = self.run_wrapper(FINPRED_SCHEDULE='10 0 * * *',
                                        SCHEDULE_TEST_NOW='2026-11-03T01:00:00+00:00')
        self.assertEqual(result.returncode, 0, result.stderr)
        routed_stage = calls[0][calls[0].index('--stage') + 1]
        with self.assertRaisesRegex(PipelineBlocked, 'outside target-day'):
            run_stage(self.base / 'runtime', routed_stage, target_date='2026-11-03',
                      clock=lambda: datetime.fromisoformat('2026-11-03T01:00:00+00:00'), client=object())
        self.assertFalse((self.base / 'runtime').exists(), 'deadline must reject before any runtime write')

    def test_manual_explicit_stage_and_target_are_preserved(self):
        result, calls = self.run_wrapper(FINPRED_EVENT_NAME='workflow_dispatch', FINPRED_STAGE='verify',
                                        FINPRED_TARGET_DATE='2026-11-04', FINPRED_SCHEDULE='10 0 * * *')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][calls[0].index('--stage') + 1], 'verify')
        self.assertEqual(calls[0][calls[0].index('--target-date') + 1], '2026-11-04')

    def test_submission_requires_exact_release_flag_and_submit_stage(self):
        for schedule in ('10 0 * * *', '20 0 * * *'):
            for released in ('', 'false', 'True', 'true'):
                with self.subTest(schedule=schedule, released=released):
                    result, calls = self.run_wrapper(FINPRED_SCHEDULE=schedule,
                                                    FINPRED_SUBMISSION_RELEASED=released)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual('--submit' in calls[0], schedule == '20 0 * * *' and released == 'true')


if __name__ == '__main__':
    unittest.main()
