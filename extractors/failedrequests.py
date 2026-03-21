from extractors.base import Extractor


class FailedRequestsExtractor(Extractor):
    def extract_information(self):
        self.result["failed_requests"] = {
            request_id: entry.to_dict()
            for request_id, entry in self.data.failed_request_log.items()
        }
