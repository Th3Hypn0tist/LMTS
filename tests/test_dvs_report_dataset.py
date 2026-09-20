from __future__ import annotations

import unittest

from lmts.dvs.report_dataset import project_percent_telemetry_dataset


def _report(report_id: str, record_id: str, score: float, cpu: float, gpu: float) -> dict:
    return {
        'format': 'lmts.report',
        'version': '1.1',
        'report': {'id': report_id},
        'records': [{
            'id': record_id,
            'coordinates': {'target': 'model-a', 'test': 'core.text_generation@1.0.0'},
            'outcome': {'result': 'pass'},
            'metrics': {'score_percent': {'value': score}},
            'evidence': {
                'telemetry': {
                    'summary': {
                        'cpu_util_percent': {'minimum': cpu - 1, 'mean': cpu, 'maximum': cpu + 1},
                        'gpus': {
                            'GPU-1': {
                                'gpu_util_percent': {'minimum': gpu - 2, 'mean': gpu, 'maximum': gpu + 2},
                                'memory_util_percent': {'minimum': 10, 'mean': 20, 'maximum': 30},
                            },
                        },
                    },
                },
            },
        }],
    }


class DVSReportDatasetTest(unittest.TestCase):
    def test_multiple_reports_and_explicit_telemetry_summaries_share_one_dataset(self) -> None:
        dataset = project_percent_telemetry_dataset([
            ('mysql:local', 'report-1', _report('report-1', 'run-1', 90, 30, 70)),
            ('mysql:local', 'report-2', _report('report-2', 'run-2', 80, 40, 60)),
        ])

        self.assertEqual(dataset['format'], 'lmts.dvs.report-telemetry-percent')
        self.assertEqual(dataset['version'], '1.0')
        self.assertEqual(dataset['report_count'], 2)
        self.assertEqual(dataset['record_count'], 2)
        self.assertEqual(dataset['row_count'], 20)

        rows = dataset['records']
        self.assertEqual({row['report_id'] for row in rows}, {'report-1', 'report-2'})
        self.assertIn('score_percent', {row['metric'] for row in rows})
        self.assertIn('cpu_util_percent', {row['metric'] for row in rows})
        self.assertIn('gpu_util_percent', {row['metric'] for row in rows})
        self.assertIn('gpu_memory_util_percent', {row['metric'] for row in rows})
        self.assertEqual(
            {row['aggregation'] for row in rows if row['metric'] == 'gpu_util_percent'},
            {'minimum', 'mean', 'maximum'},
        )

    def test_duplicate_identical_report_is_not_visualized_twice(self) -> None:
        report = _report('report-1', 'run-1', 90, 30, 70)
        dataset = project_percent_telemetry_dataset([
            ('mysql:a', 'report-1', report),
            ('mysql:b', 'report-1', report),
        ])
        self.assertEqual(dataset['report_count'], 1)
        self.assertEqual(dataset['record_count'], 1)


if __name__ == '__main__':
    unittest.main()
