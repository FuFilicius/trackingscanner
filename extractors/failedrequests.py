from extractors.base import Extractor


class FailedRequestsExtractor(Extractor):
    def extract_information(self):
        self.result["failed_requests"] = self.data.failed_request_log