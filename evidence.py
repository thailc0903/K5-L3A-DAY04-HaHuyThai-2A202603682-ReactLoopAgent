"""Kiểm tra phần bằng chứng còn thiếu từ câu hỏi và observations, không đọc eval."""
import re
import unicodedata
from urllib.parse import urlsplit


def _fold(text):
    text = unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
    return ''.join(c for c in text if not unicodedata.combining(c))


class EvidenceCoverage:
    """Kiểm tra status, chi tiết incident và liên kết theo yêu cầu người dùng."""

    def __init__(self, question, schemas):
        functions = {s['function']['name']: s['function'] for s in schemas}
        details = functions.get('get_incident_details', {})
        providers = details.get('parameters', {}).get('properties', {}).get('provider', {}).get('enum', [])
        self.status_tools = {}
        for provider in providers:
            name = f'get_{provider}_status'
            if name in functions:
                self.status_tools[provider] = name
            elif 'get_status' in functions:
                self.status_tools[provider] = 'get_status'
        text = _fold(question)
        # Không biến câu cấm suy diễn nhân quả thành yêu cầu đọc root cause.
        positive = re.split(r'\b(?:khong|dung)\s+(?:suy|tao|ket luan|khang dinh)\b', text, 1)[0]
        positive = re.sub(r'\b(?:khong|dung)\s+(?:can\s+)?(?:kiem tra|goi tool|dung tool)\b[^.!?;\n]*',
                          '', positive)
        self.requested = {p for p in self.status_tools if re.search(r'\b' + re.escape(p) + r'\b', positive)}
        self.wants_status = bool(re.search(
            r'\b(?:status|current|hien tai|hien co|kiem tra snapshot)\b'
            r'|\b(?:tong hop|kiem tra|xem|check)\b.{0,30}\btrang thai\b'
            r'|\bdang\s+(?:outage|bi loi|operational)\b', positive))
        if re.search(r'\b(?:khong can|without)\s+(?:kiem tra\s+)?status\b', positive):
            self.wants_status = False
        self.wants_details = bool(re.search(r'\b(?:incident|su co)\b', positive) and re.search(
            r'\b(?:chi tiet|timeline|dong thoi gian|dien bien|anh huong|pham vi|nguyen nhan'
            r'|doi chieu|so sanh|scope|impact|root cause|compare)\b', positive))
        self.wants_links = bool(re.search(
            r'\b(?:theo|doc|mo|follow|read|open)\b.{0,45}\b(?:lien ket|link|linked)\b'
            r'|\b(?:incident gop|combined summary)\b', positive))
        self.status_attempts = set()
        self.detail_attempts = set()
        self.incidents = {}
        self.related = set()

    def observe(self, name, arguments, result):
        provider = arguments.get('provider')
        for target, tool in self.status_tools.items():
            if name == tool and (tool != 'get_status' or provider == target):
                provider = target
                if result.get('error') not in ('INVALID_ARGUMENTS', 'INVALID_TOOL_RESULT', 'UNKNOWN_TOOL'):
                    self.status_attempts.add(target)
                entries = result.get('incidents')
                if isinstance(entries, list):
                    self.incidents[target] = [i['id'] for i in entries
                                              if isinstance(i, dict) and isinstance(i.get('id'), str)]
                return
        if name != 'get_incident_details' or not isinstance(provider, str):
            return
        incident_id = arguments.get('incident_id')
        if not isinstance(incident_id, str) or provider not in self.status_tools:
            return
        if result.get('error') not in ('INVALID_ARGUMENTS', 'INVALID_TOOL_RESULT', 'UNKNOWN_TOOL'):
            self.detail_attempts.add((provider, incident_id))
        if not self.wants_links or result.get('ok') is not True:
            return
        updates = result.get('updates')
        if not isinstance(updates, list):
            return
        for update in updates:
            body = update.get('body') if isinstance(update, dict) else None
            if not isinstance(body, str):
                continue
            for url in re.findall(r'https?://[^\s<>"\']+', body):
                try:
                    parsed = urlsplit(url)
                    match = re.fullmatch(r'/incidents/([A-Za-z0-9_-]+)/?', parsed.path)
                    host = parsed.hostname or ''
                except ValueError:
                    continue
                # Không mở URL bên ngoài; chỉ tra ID bằng tool của provider hỗ trợ.
                target = next((p for p in self.status_tools if p in host), None)
                if target and match:
                    self.related.add((target, match.group(1)))

    def missing(self):
        missing = []
        if self.wants_status:
            for provider in sorted(self.requested - self.status_attempts):
                missing.append({'requirement': 'service_status', 'provider': provider,
                                'tool': self.status_tools[provider]})
        if self.wants_details:
            read_providers = {p for p, _ in self.detail_attempts}
            for provider in sorted(self.requested):
                candidates = self.incidents.get(provider, [])
                if candidates and provider not in read_providers:
                    missing.append({'requirement': 'incident_details', 'provider': provider,
                                    'tool': 'get_incident_details', 'observed_ids': candidates})
        if self.wants_links:
            for provider, incident_id in sorted(self.related - self.detail_attempts):
                missing.append({'requirement': 'linked_incident', 'provider': provider,
                                'tool': 'get_incident_details', 'incident_id': incident_id})
        return missing
