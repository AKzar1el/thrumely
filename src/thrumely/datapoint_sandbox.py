from __future__ import annotations

import argparse
import json
from typing import Mapping

from .datapoint_client import DatapointClient
from .datapoint_protocol import build_pairwise_sandbox_job, build_rating_sandbox_job
from .datapoint_results import normalize_comparison_results, normalize_public_responses, normalize_rating_results


class _OfflineFakeTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method: str, url: str, headers: Mapping[str, str], body: bytes | None, content_type: str | None):
        self.calls.append((method, url, dict(headers), body, content_type))
        path = url.split('/data-labelling/v1', 1)[1]
        if method == 'POST' and path == '/jobs':
            payload = json.loads((body or b'{}').decode('utf-8'))
            assert payload['serving_environment'] == 'sandbox'
            job_id = 'job_cmp' if payload['task_type'] == 'comparison' else 'job_rate'
            return 200, json.dumps({'job_id': job_id, 'name': payload['name'], 'task_type': payload['task_type'], 'serving_environment': 'sandbox', 'estimated_cost_credits': 0, 'credits_per_response': 0}).encode()
        if method == 'GET' and path in {'/jobs/job_cmp', '/jobs/job_rate'}:
            task_type = 'comparison' if path.endswith('job_cmp') else 'rating'
            return 200, json.dumps({'job_id': path.rsplit('/', 1)[1], 'task_type': task_type, 'status': 'completed', 'serving_environment': 'sandbox', 'total_datapoints': 1, 'completed_datapoints': 1, 'total_responses': 5, 'max_responses_per_datapoint': 5, 'cost_credits': 0, 'credits_per_response': 0, 'refundable_credits': 0, 'errors': []}).encode()
        if method == 'GET' and path == '/jobs/job_cmp/results':
            return 200, json.dumps({'job_id': 'job_cmp', 'status': 'completed', 'task_type': 'comparison', 'results': [{'datapoint_index': 0, 'votes': {'A': 4, 'B': 1}, 'total_responses': 5, 'consensus': 'A', 'confidence': 0.8, 'agreement_rate': 0.8, 'media': [{'media_id': 'm_a', 'role': 'candidates', 'url': '/signed/a'}, {'media_id': 'm_b', 'role': 'candidates', 'url': '/signed/b'}]}]}).encode()
        if method == 'GET' and path == '/jobs/job_rate/results':
            return 200, json.dumps({'job_id': 'job_rate', 'status': 'completed', 'task_type': 'rating', 'results': [{'datapoint_index': 0, 'mean': 4.0, 'median': 4, 'distribution': {'3': 1, '4': 3, '5': 1}, 'total_responses': 5, 'weighted_mean': 4.0, 'weighted_distribution': {'3': 1.0, '4': 3.0, '5': 1.0}}]}).encode()
        if method == 'GET' and path in {'/jobs/job_cmp/responses', '/jobs/job_rate/responses'}:
            task_type = 'comparison' if 'job_cmp' in path else 'rating'
            response = 'A' if task_type == 'comparison' else '4'
            return 200, json.dumps({'job_id': 'job_cmp' if task_type == 'comparison' else 'job_rate', 'task_type': task_type, 'responses': [{'datapoint_index': 0, 'response': response, 'response_label': response, 'response_time_ms': 2500, 'annotator_id': 'anon_0000000001', 'annotator_country': 'US', 'annotator_region': 'CA', 'annotator_city': 'San Francisco', 'timestamp': '2026-09-01 00:00:00+00:00'}]}).encode()
        return 404, json.dumps({'error': 'not found'}).encode()


def run_offline_sandbox() -> dict[str, object]:
    transport = _OfflineFakeTransport()
    client = DatapointClient('dp_test_fixture', transport=transport)
    pairwise_payload = build_pairwise_sandbox_job('thrumely-offline-pairwise', [{'context': 'Create a red mug on a white table.', 'candidate_a': 'dp://aaaaaaaaaaaa/a.png', 'candidate_b': 'dp://bbbbbbbbbbbb/b.png'}])
    rating_payload = build_rating_sandbox_job('thrumely-offline-rating', [{'context': 'Create a red mug on a white table.', 'subject': 'dp://aaaaaaaaaaaa/a.png'}])

    pairwise_create = client.create_sandbox_job(pairwise_payload)
    rating_create = client.create_sandbox_job(rating_payload)
    pairwise_status = client.get_job(str(pairwise_create['job_id']))
    rating_status = client.get_job(str(rating_create['job_id']))
    pairwise_results_raw = client.get_results(str(pairwise_create['job_id']))
    rating_results_raw = client.get_results(str(rating_create['job_id']))
    pairwise_responses_raw = client.get_responses(str(pairwise_create['job_id']))
    rating_responses_raw = client.get_responses(str(rating_create['job_id']))

    return {'mode': 'OFFLINE_FAKE_SANDBOX', 'network_calls': 0, 'jobs_created': 2, 'pairwise': {'serving_environment': pairwise_status['serving_environment'], 'cost_credits': pairwise_status['cost_credits'], 'normalized_results': normalize_comparison_results(pairwise_results_raw), 'public_responses': normalize_public_responses(pairwise_responses_raw)}, 'rating': {'serving_environment': rating_status['serving_environment'], 'cost_credits': rating_status['cost_credits'], 'normalized_results': normalize_rating_results(rating_results_raw), 'public_responses': normalize_public_responses(rating_responses_raw)}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Thrumely Datapoint sandbox integration smoke')
    parser.add_argument('--offline', action='store_true', help='run deterministic fake sandbox with no credentials/network')
    args = parser.parse_args(argv)
    if not args.offline:
        parser.error('only --offline is enabled in the zero-cost integration slice')
    print(json.dumps(run_offline_sandbox(), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
