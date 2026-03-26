from extractors.base import Extractor
from utils import get_corresponding_response


class RequestsExtractor(Extractor):
    def extract_information(self):
        summary = {
            "total": 0,
            "with_response": 0,
            "set_cookie": 0,
            "methods": {},
            "resource_types": {},
            "status_classes": {},
        }

        for request in self.data.request_log.values():
            summary["total"] += 1
            response = get_corresponding_response(request.request_id, self.data)


            self._increase_counter(summary["methods"], request.method)

            resource_type = response.resource_type if response else request.resource_type
            self._increase_counter(summary["resource_types"], resource_type)

            if response is not None:
                summary["with_response"] += 1
                status_class = f"{response.status // 100}xx"
                self._increase_counter(summary["status_classes"], status_class)

            if self._get_sets_cookie(response):
                summary["set_cookie"] += 1

        self.result["requests"] = summary

    @staticmethod
    def _get_sets_cookie(response):
        if response is None:
            return False
        return "set-cookie" in response.headers_lower

    @staticmethod
    def _increase_counter(counter_dict, key):
        if not key:
            key = "unknown"
        counter_dict[key] = counter_dict.get(key, 0) + 1
