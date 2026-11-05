"""Independent containment checks for the separate course deployment policy."""

import json
from pathlib import Path
import tempfile
import unittest

from finpred.pipelines import course_benchmark as policy
from finpred.pipelines.daily import PipelineBlocked


class CourseBenchmarkContainmentAudit(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / 'runtime'
        self.root.mkdir(mode=0o700)

    def test_relative_parent_escape_cannot_read_outside_evidence(self):
        outside = self.base / 'outside.json'
        outside.write_text(json.dumps({'outside': True}))
        outside.chmod(0o600)
        with self.assertRaises(PipelineBlocked):
            policy._read_json(self.root / '..' / 'outside.json', self.root)

    def test_relative_parent_escape_cannot_create_outside_artifacts(self):
        outside = self.base / 'outside-artifacts'
        with self.assertRaises(PipelineBlocked):
            policy._directory(self.root / '..' / outside.name, self.root)
        self.assertFalse(outside.exists())

    def test_symlink_cannot_redirect_an_inside_evidence_file(self):
        outside = self.base / 'outside.json'
        outside.write_text('{}')
        outside.chmod(0o600)
        alias = self.root / 'alias.json'
        alias.symlink_to(outside)
        with self.assertRaises(PipelineBlocked):
            policy._read_json(alias, self.root)

    def test_canonical_private_evidence_remains_readable(self):
        destination = policy._directory(self.root / 'candidates' / policy.POLICY, self.root)
        evidence = destination / 'evidence.json'
        evidence.write_text(json.dumps({'deployment_policy': policy.POLICY}))
        evidence.chmod(0o600)
        self.assertEqual({'deployment_policy': policy.POLICY}, policy._read_json(evidence, self.root))


if __name__ == '__main__':
    unittest.main()
