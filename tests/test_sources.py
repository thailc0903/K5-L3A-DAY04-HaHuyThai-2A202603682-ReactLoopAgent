"""Kiểm chứng kiểm tra nguồn với nhiều incident và giới hạn lượt sửa."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from status_tools import StatusTools
from test_lab import FakeProvider, final, tool_call


class SourceValidationTests(unittest.TestCase):
    def test_each_successful_incident_needs_its_observed_url(self):
        tools = StatusTools()
        github_url = tools.get_incident_details('github', 'xr3myzj7ms51')['url']
        cloudflare_url = tools.get_incident_details('cloudflare', 'wp49bp8bqo6c')['url']
        first = tool_call('a', 'get_incident_details',
                          '{"provider":"github","incident_id":"xr3myzj7ms51"}')
        second = tool_call('b', 'get_incident_details',
                           '{"provider":"cloudflare","incident_id":"wp49bp8bqo6c"}')
        first['calls'] += second['calls']
        first['message']['tool_calls'] += second['message']['tool_calls']
        provider = FakeProvider([first, final('Nguồn GitHub: ' + github_url),
                                 final('Nguồn: ' + github_url + ' ' + cloudflare_url)])
        result = run_agent('So sánh hai incident', provider, tools, max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertIn(github_url, result['answer'])
        self.assertIn(cloudflare_url, result['answer'])
        validations = [event for event in result['trace']
                       if event['event'] == 'validation_missing_source']
        self.assertEqual(len(validations), 1)
        self.assertEqual(validations[0]['missing_urls'], [cloudflare_url])
        correction = provider.histories[2][-1]
        self.assertEqual(correction['role'], 'user')
        self.assertIn(cloudflare_url, correction['content'])

    def test_failed_incident_does_not_require_a_url_even_if_returned(self):
        tools = StatusTools()
        provider = FakeProvider([
            tool_call('a', 'get_incident_details',
                      '{"provider":"github","incident_id":"missing"}'),
            final('Không xác minh được incident.'),
        ])
        with patch.object(tools, 'execute', return_value={
                'ok': False, 'error': 'INCIDENT_NOT_FOUND',
                'url': 'https://example.invalid/not-confirmed'}):
            result = run_agent('Kiểm tra ID', provider, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(any(event['event'] == 'validation_missing_source'
                             for event in result['trace']))

    def test_repeated_missing_sources_stop_at_budget(self):
        provider = FakeProvider([
            tool_call('a', 'get_incident_details',
                      '{"provider":"github","incident_id":"xr3myzj7ms51"}'),
            final('Chưa có nguồn.'), final('Vẫn thiếu nguồn.'),
        ])
        result = run_agent('Kiểm tra incident', provider, StatusTools(), max_steps=3)
        self.assertEqual(result['status'], 'max_steps')
        self.assertEqual(result['answer'], '')
        self.assertEqual(len(provider.histories), 3)
        self.assertEqual(result['trace'][-1]['event'], 'max_steps')
        self.assertEqual(sum(event['event'] == 'validation_missing_source'
                             for event in result['trace']), 2)

    def test_repeated_incident_only_requires_its_url_once(self):
        tools = StatusTools()
        url = tools.get_incident_details('github', 'xr3myzj7ms51')['url']
        first = tool_call('a', 'get_incident_details',
                          '{"provider":"github","incident_id":"xr3myzj7ms51"}')
        second = tool_call('b', 'get_incident_details',
                           '{"provider":"github","incident_id":"xr3myzj7ms51"}')
        provider = FakeProvider([first, second, final('Nguồn: ' + url)])
        result = run_agent('Kiểm tra', provider, tools, max_steps=3)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(any(event['event'] == 'validation_missing_source'
                             for event in result['trace']))


if __name__ == '__main__':
    unittest.main()
