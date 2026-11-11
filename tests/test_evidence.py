"""Regression tests cho việc dừng khi chưa kiểm tra đủ bằng chứng được hỏi."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent import run_agent
from bonus.test_agent import ScriptedProvider, call, final
from bonus.tools import BonusTools
from evidence import EvidenceCoverage
from status_tools import SCHEMAS, StatusTools


class EvidenceCoverageTests(unittest.TestCase):
    def test_explicit_request_not_to_check_status_does_not_force_tools(self):
        provider = ScriptedProvider([final('Đây là giải thích khái niệm vòng lặp.')])
        result = run_agent('Giải thích vòng lặp, không cần kiểm tra status GitHub hoặc npm.',
                           provider, BonusTools(), max_steps=1)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(provider.histories), 1)

    def test_historical_timeline_question_does_not_require_upstream_status(self):
        coverage = EvidenceCoverage('Tra timeline Vercel incident: update nào nhắc GitHub upstream? '
                                    'Sự cố đó đang xảy ra không?', BonusTools.schemas)
        coverage.observe('get_incident_details', {'provider': 'vercel', 'incident_id': 'historical'},
                         {'ok': True, 'updates': []})
        self.assertEqual(coverage.missing(), [])

    def test_current_status_is_not_replaced_by_a_resolved_incident(self):
        tools = StatusTools()
        incident = tools.get_status('github', 'Actions')['incidents'][1]['id']
        detail = tools.get_incident_details('github', incident)
        provider = ScriptedProvider([
            call('detail', 'get_incident_details', {'provider': 'github', 'incident_id': incident}),
            final('Chỉ biết incident đã resolved. ' + detail['url']),
            call('status', 'get_status', {'provider': 'github', 'component': 'Actions'}),
            final('Actions operational trong snapshot. ' + detail['url']),
        ])
        result = run_agent('GitHub Actions đang outage vì incident này? Hãy kiểm tra snapshot.',
                           provider, tools, max_steps=4)
        self.assertEqual(result['status'], 'completed')
        checks = [t for t in result['trace'] if t['event'] == 'validation_incomplete_evidence']
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['missing'][0]['requirement'], 'service_status')
        self.assertEqual(checks[0]['missing'][0]['provider'], 'github')
        revision = provider.histories[2][-1]
        self.assertEqual(revision['role'], 'user')
        self.assertIn('get_status', revision['content'])

    def test_missing_status_at_budget_limit_is_not_completed(self):
        tools = StatusTools()
        incident = tools.get_status('github', 'Actions')['incidents'][0]['id']
        detail = tools.get_incident_details('github', incident)
        provider = ScriptedProvider([
            call('detail', 'get_incident_details', {'provider': 'github', 'incident_id': incident}),
            final('Chỉ biết lịch sử. ' + detail['url']),
        ])
        result = run_agent('Kiểm tra status GitHub và incident đã nêu.', provider, tools, max_steps=2)
        self.assertEqual(result['status'], 'max_steps')
        self.assertEqual(result['answer'], '')
        self.assertEqual(len(result['usage']), 2)

    def test_link_check_uses_observed_id_not_a_fixed_incident(self):
        coverage = EvidenceCoverage('Theo liên kết incident GitHub để tìm nguyên nhân.', SCHEMAS)
        original = {'provider': 'github', 'incident_id': 'first-example'}
        linked = 'new-linked-example'
        coverage.observe('get_incident_details', original, {
            'ok': True, 'updates': [{'body': 'Related incident: https://www.githubstatus.com/incidents/' + linked}],
        })
        self.assertEqual(coverage.missing(), [{
            'requirement': 'linked_incident', 'provider': 'github',
            'tool': 'get_incident_details', 'incident_id': linked,
        }])
        coverage.observe('get_incident_details', {'provider': 'github', 'incident_id': linked},
                         {'ok': False, 'error': 'INCIDENT_NOT_FOUND'})
        self.assertEqual(coverage.missing(), [])

    def test_failed_status_can_end_with_an_honest_partial_answer(self):
        tools = StatusTools(fail=True)
        provider = ScriptedProvider([call('a', 'get_status', {'provider': 'cloudflare'}),
                                     final('Cloudflare chưa xác nhận vì timeout.')])
        result = run_agent('Kiểm tra status Cloudflare.', provider, tools)
        self.assertEqual(result['status'], 'completed')
        self.assertFalse(any(t['event'] == 'validation_incomplete_evidence' for t in result['trace']))

    def test_summary_does_not_replace_details_for_each_provider(self):
        tools = BonusTools()
        selected = {}
        for provider, component in [('vercel', 'Builds'), ('npm', 'publishing')]:
            incident = tools.execute('get_' + provider + '_status', {'component': component})['incidents'][0]['id']
            selected[provider] = {'provider': provider, 'incident_id': incident, 'limit': 3}
        urls = [tools.execute('get_incident_details', args)['url'] for args in selected.values()]
        first = call('vercel', 'get_vercel_status', {'component': 'Builds'})
        second = call('npm', 'get_npm_status', {'component': 'publishing'})
        first['calls'] += second['calls']
        first['message']['tool_calls'] += second['message']['tool_calls']
        provider = ScriptedProvider([
            first, final('Chỉ mới có danh sách tóm tắt.'),
            call('vercel-detail', 'get_incident_details', selected['vercel']),
            final('Mới có một bên. ' + urls[0]),
            call('npm-detail', 'get_incident_details', selected['npm']),
            final('Hai incident đã resolved. ' + ' '.join(urls)),
        ])
        result = run_agent('Đối chiếu incident Vercel và npm: phạm vi, thời gian, nguồn.',
                           provider, tools, max_steps=6)
        self.assertEqual(result['status'], 'completed')
        checks = [t['missing'] for t in result['trace'] if t['event'] == 'validation_incomplete_evidence']
        self.assertEqual({x['provider'] for x in checks[0]}, {'vercel', 'npm'})
        self.assertEqual([x['provider'] for x in checks[1]], ['npm'])

    def test_negative_causality_instruction_does_not_require_incident_details(self):
        tools = BonusTools()
        coverage = EvidenceCoverage('Tổng hợp status GitHub và npm, không suy luận sự cố có chung nguyên nhân.',
                                    tools.schemas)
        for provider in ['github', 'npm']:
            name = 'get_' + provider + '_status'
            coverage.observe(name, {}, tools.execute(name, {}))
        self.assertEqual(coverage.missing(), [])

    def test_historical_incident_comparison_does_not_force_current_status(self):
        coverage = EvidenceCoverage('So sánh incident GitHub và npm: thời gian, trạng thái, ảnh hưởng.',
                                    BonusTools.schemas)
        for provider in ['github', 'npm']:
            coverage.observe('get_incident_details', {'provider': provider, 'incident_id': 'historical'},
                             {'ok': True, 'updates': []})
        self.assertEqual(coverage.missing(), [])

    def test_unsupported_providers_do_not_trigger_unavailable_tools(self):
        provider = ScriptedProvider([final('Không có tools hoặc bằng chứng cho hai provider đó.')])
        result = run_agent('Xác nhận status Linear và Slack hiện tại.', provider, BonusTools())
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(len(provider.histories), 1)

    def test_invalid_arguments_do_not_count_as_a_status_check(self):
        coverage = EvidenceCoverage('Kiểm tra status GitHub.', SCHEMAS)
        coverage.observe('get_status', {'provider': 'github'}, {'ok': False, 'error': 'INVALID_ARGUMENTS'})
        self.assertEqual(coverage.missing()[0]['requirement'], 'service_status')


if __name__ == '__main__':
    unittest.main()
