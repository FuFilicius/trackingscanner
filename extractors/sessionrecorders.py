import json
from pathlib import Path

from extractors.base import Extractor


def _load_session_recorder_patterns() -> list[str]:
	resource_path = Path(__file__).resolve().parent.parent / 'resources' / 'session_recorders.json'
	with resource_path.open('r', encoding='utf-8') as file:
		patterns = json.load(file)
	return [pattern.lower() for pattern in patterns if isinstance(pattern, str) and pattern]


SESSION_RECORDER_PATTERNS = _load_session_recorder_patterns()


class SessionRecordersExtractor(Extractor):
	def extract_information(self):
		session_recorders = {
			'session_recording': False,
			'services': [],
		}

		matches_found = set()

		for request in self.data.request_log.values():
			parsed_url = request.parsed_url
			host = (parsed_url.hostname or parsed_url.netloc).lower()
			path = parsed_url.path.lower()
			clean_url = f'{host}{path}'

			for pattern in SESSION_RECORDER_PATTERNS:
				if pattern in clean_url:
					matches_found.add(pattern)

		if matches_found:
			session_recorders['session_recording'] = True
			session_recorders['services'] = sorted(matches_found)

		self.result['session_recorders'] = session_recorders

