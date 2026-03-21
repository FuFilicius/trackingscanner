from extractors.base import Extractor
from utils import get_corresponding_response


class RequestsExtractor(Extractor):
    def extract_information(self):
        requests = []

        for request in self.data.request_log.values():
            response = get_corresponding_response(request.request_id, self.data)

            request_dict = {
                'timestamp': request.timestamp,
                'request_id': request.request_id,
                'url': request.url,
                'set_cookie': self._get_sets_cookie(response),
                'method': request.method,
                'request_headers': request.headers,
                'response_headers': response.headers if response else None,
                'status': response.status if response else None,
                'status_text': response.status_text if response else None,
                'resource_type': response.resource_type if response else None,
            }

            request_dict['is_thirdparty'] = request.is_thirdparty

            requests.append(request_dict)

        self.result['requests'] = requests

    @staticmethod
    def _get_sets_cookie(response):
        if response is None:
            return False
        return 'set-cookie' in response.headers_lower
