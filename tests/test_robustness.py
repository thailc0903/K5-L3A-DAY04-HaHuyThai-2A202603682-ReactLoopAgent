"""Regression tests CP3: provider giả lập, tools snapshot, không gọi LLM API."""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'evals'))

from agent import run_agent
from scenarios import ScenarioTools
from status_tools import StatusTools
from test_lab import FakeProvider, final, tool_call


class RobustnessTests(unittest.TestCase):
    def test_normalized_call_cannot_change_native_name_or_arguments(self):
        original = tool_call('same-id', 'get_status', '{"provider":"github"}')
        for field, value in [('name', 'get_incident_details'),
                             ('arguments', '{"provider":"cloudflare"}')]:
            response = copy.deepcopy(original)
            response['calls'][0][field] = value
            tools = StatusTools()
            with patch.object(tools, 'execute') as execute:
                result = run_agent('Kiểm tra', FakeProvider([response]), tools)
            self.assertEqual(result['status'], 'error')
            self.assertEqual(result['trace'][-1]['error'], 'INVALID_MODEL_RESPONSE')
            execute.assert_not_called()

    def test_non_finite_json_arguments_are_rejected_before_execution(self):
        for constant in ('NaN', 'Infinity', '-Infinity'):
            response = tool_call('bad', 'get_status',
                                 '{"provider":"github","component":' + constant + '}')
            provider = FakeProvider([response, final('Không lấy được dữ liệu hợp lệ.')])
            tools = StatusTools()
            with patch.object(tools, 'execute') as execute:
                result = run_agent('Kiểm tra', provider, tools)
            self.assertEqual(result['status'], 'completed')
            execute.assert_not_called()
            self.assertEqual(json.loads(provider.histories[1][-1]['content'])['error'],
                             'INVALID_ARGUMENTS')

    def test_status_observation_exposes_scope_without_changing_tool_trace(self):
        provider = FakeProvider([tool_call('a', 'get_status', '{"provider":"github"}'), final()])
        result = run_agent('Kiểm tra tổng quan', provider, StatusTools())
        raw = next(t['result'] for t in result['trace'] if t['event'] == 'tool')
        received = json.loads(provider.histories[1][-1]['content'])
        self.assertEqual(received['overall'], raw['overall'])
        self.assertEqual(received['components'], [])
        self.assertFalse(received['agent_evidence_scope']['all_components_checked'])
        self.assertEqual(received['agent_evidence_scope']['components_returned'], 0)
        self.assertNotIn('agent_evidence_scope', raw)

    def test_invalid_budget_is_traced_without_calling_provider(self):
        for budget in (0, -1, True, 1.5, '2'):
            with self.subTest(budget=budget):
                provider = FakeProvider([])
                result = run_agent('Kiểm tra', provider, StatusTools(), budget)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['trace'][-1]['error'], 'INVALID_MAX_STEPS')
                self.assertEqual(provider.histories, [])

    def test_provider_failures_stop_without_leaking_exception_text(self):
        secret = 'dummy-sensitive-provider-value'
        for error_type in (RuntimeError, TimeoutError, ConnectionError, KeyError, TypeError):
            with self.subTest(error_type=error_type.__name__):
                provider = FakeProvider([])
                with patch.object(provider, 'complete', side_effect=error_type(secret)) as complete:
                    result = run_agent('Kiểm tra', provider, StatusTools())
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['trace'][-1]['error'], 'PROVIDER_ERROR')
                self.assertNotIn(secret, json.dumps(result))
                self.assertEqual(complete.call_count, 1)

    def test_malformed_response_does_not_crash_or_send_bad_call_ids(self):
        mismatched = tool_call('a', 'get_status', '{"provider":"github"}')
        mismatched['message']['tool_calls'][0]['id'] = 'other-id'
        bad_call = tool_call('a', 'get_status', '{}')
        bad_call['calls'] = [None]
        for response in (None, {}, final(['not text']), mismatched, bad_call):
            with self.subTest(response=response):
                tools = StatusTools()
                with patch.object(tools, 'execute') as execute:
                    result = run_agent('Kiểm tra', FakeProvider([response]), tools)
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['trace'][-1]['error'], 'INVALID_MODEL_RESPONSE')
                execute.assert_not_called()

    def test_truncated_tool_call_is_not_executed(self):
        response = tool_call('a', 'get_status', '{"provider":"github"}')
        response['finish'] = 'length'
        response['usage'] = {'total_tokens': 20}
        tools = StatusTools()
        with patch.object(tools, 'execute') as execute:
            result = run_agent('Kiểm tra', FakeProvider([response]), tools)
        execute.assert_not_called()
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['usage'], [{'total_tokens': 20}])
        self.assertEqual(result['trace'][-1]['error'], 'MODEL_STOPPED')

    def test_unexpected_finish_is_traced_as_error(self):
        for finish in ('content_filter', None, 'unknown'):
            with self.subTest(finish=finish):
                response = final('Nội dung chưa được xác nhận')
                response['finish'] = finish
                result = run_agent('Kiểm tra', FakeProvider([response]), StatusTools())
                self.assertEqual(result['status'], 'error')
                self.assertEqual(result['answer'], '')
                self.assertEqual(result['trace'][-1]['error'], 'MODEL_STOPPED')

    def test_empty_answer_and_missing_calls_are_not_completed(self):
        responses = [final(''), final('  '), final(None), final()]
        responses[-1]['finish'] = 'tool_calls'
        for response in responses:
            with self.subTest(response=response):
                result = run_agent('Kiểm tra', FakeProvider([response]), StatusTools())
                self.assertEqual(result['status'], 'error')
                self.assertIn(result['trace'][-1]['error'], ('EMPTY_ANSWER', 'MISSING_TOOL_CALLS'))

    def test_invalid_arguments_are_observations_and_can_be_corrected(self):
        for arguments in ('{', '[]', 'null', 'true', '42', {'provider': 'github'}):
            with self.subTest(arguments=arguments):
                bad = tool_call('bad', 'get_status', arguments)
                good = tool_call('good', 'get_status', '{"provider":"github"}')
                provider = FakeProvider([bad, good, final('Đã đọc được GitHub.')])
                result = run_agent('Kiểm tra', provider, StatusTools())
                self.assertEqual(result['status'], 'completed')
                error = json.loads(provider.histories[1][-1]['content'])
                self.assertEqual(error['error'], 'INVALID_ARGUMENTS')
                success = json.loads(provider.histories[2][-1]['content'])
                self.assertEqual(success['provider'], 'github')
                self.assertEqual(provider.histories[1][-1]['tool_call_id'], 'bad')
                self.assertEqual(provider.histories[2][-1]['tool_call_id'], 'good')

    def test_unknown_tool_invalid_provider_and_timeout_return_to_model(self):
        calls = [tool_call('unknown', 'missing_tool', '{}'),
                 tool_call('invalid', 'get_status', '{"provider":"unsupported"}'),
                 tool_call('timeout', 'get_status', '{"provider":"cloudflare"}'),
                 tool_call('success', 'get_status', '{"provider":"github"}')]
        response = calls[0]
        response['calls'] = [item['calls'][0] for item in calls]
        response['message']['tool_calls'] = [item['message']['tool_calls'][0] for item in calls]
        provider = FakeProvider([response, final('GitHub có dữ liệu; Cloudflare chưa xác nhận.')])
        result = run_agent('Kiểm tra cả hai', provider, ScenarioTools('cloudflare_timeout'), 2)
        self.assertEqual(result['status'], 'completed')
        observations = [json.loads(message['content']) for message in provider.histories[1][-4:]]
        self.assertEqual([item['error'] for item in observations[:3]],
                         ['UNKNOWN_TOOL', 'ValueError', 'TimeoutError'])
        self.assertEqual(observations[3]['provider'], 'github')
        self.assertEqual([message['tool_call_id'] for message in provider.histories[1][-4:]],
                         ['unknown', 'invalid', 'timeout', 'success'])

    def test_raised_tool_error_does_not_drop_other_calls_or_leak_text(self):
        first = tool_call('fail', 'get_status', '{"provider":"cloudflare"}')
        second = tool_call('ok', 'get_status', '{"provider":"github"}')
        first['calls'] += second['calls']
        first['message']['tool_calls'] += second['message']['tool_calls']
        provider = FakeProvider([first, final('Chỉ kiểm tra được GitHub.')])
        tools = StatusTools()
        execute = tools.execute

        def fail_cloudflare(name, arguments):
            if arguments.get('provider') == 'cloudflare':
                raise TimeoutError('dummy-sensitive-tool-value')
            return execute(name, arguments)

        with patch.object(tools, 'execute', side_effect=fail_cloudflare):
            result = run_agent('Kiểm tra', provider, tools)
        self.assertEqual(result['status'], 'completed')
        observations = [json.loads(message['content']) for message in provider.histories[1][-2:]]
        self.assertEqual(observations[0]['error'], 'TimeoutError')
        self.assertEqual(observations[1]['provider'], 'github')
        self.assertNotIn('dummy-sensitive-tool-value', json.dumps(result))

    def test_invalid_tool_result_is_a_serializable_observation(self):
        for output in (None, [], {'value': object()}, {'value': float('nan')}):
            with self.subTest(output=output):
                provider = FakeProvider([tool_call('a', 'get_status', '{}'), final('Tool không trả dữ liệu hợp lệ.')])
                tools = StatusTools()
                with patch.object(tools, 'execute', return_value=output):
                    result = run_agent('Kiểm tra', provider, tools)
                self.assertEqual(result['status'], 'completed')
                observation = json.loads(provider.histories[1][-1]['content'])
                self.assertEqual(observation['error'], 'INVALID_TOOL_RESULT')
                json.dumps(result, allow_nan=False)

    def test_budget_counts_model_calls_and_traces_exhaustion(self):
        first = tool_call('a', 'get_status', '{"provider":"github"}')
        second = tool_call('b', 'get_status', '{"provider":"cloudflare"}')
        first['calls'] += second['calls']
        first['message']['tool_calls'] += second['message']['tool_calls']
        provider = FakeProvider([first])
        result = run_agent('Kiểm tra', provider, StatusTools(), max_steps=1)
        self.assertEqual(result['status'], 'max_steps')
        self.assertEqual(len(provider.histories), 1)
        tools = [event for event in result['trace'] if event['event'] == 'tool']
        self.assertEqual([event['tool_call_id'] for event in tools], ['a', 'b'])
        self.assertEqual([event['step'] for event in tools], [1, 1])
        self.assertEqual(result['trace'][-1]['event'], 'max_steps')

    def test_assistant_message_and_usage_survive_multiple_steps(self):
        response = tool_call('a', 'get_status', '{"provider":"github"}')
        response['message']['content'] = 'Đang kiểm tra.'
        response['message']['refusal'] = None
        original = copy.deepcopy(response['message'])
        response['usage'] = {'total_tokens': 12}
        answer = final('Đã kiểm tra.')
        answer['usage'] = {'total_tokens': 15}
        provider = FakeProvider([response, answer])
        result = run_agent('Kiểm tra', provider, StatusTools())
        self.assertEqual(provider.histories[1][-2], original)
        self.assertEqual(response['message'], original)
        self.assertEqual(result['usage'], [{'total_tokens': 12}, {'total_tokens': 15}])


if __name__ == '__main__':
    unittest.main()
