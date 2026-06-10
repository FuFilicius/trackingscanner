from extractors.base import Extractor
from scanner_tools.results import CountByKey, FailedRequestsSummary
from utils import parse_domain


class FailedRequestsExtractor(Extractor):
    def extract_information(self) -> None:
        summary: FailedRequestsSummary = {
            "total": 0,
            "by_error": {},
            "by_method": {},
            "by_resource_type": {},
            "counts_by_fqdn": {},
        }

        for entry in self.data.failed_request_log.values():
            summary["total"] += 1
            self._increase_counter(summary["by_method"], entry.method)
            self._increase_counter(summary["by_resource_type"], entry.resource_type)
            self._increase_counter(
                summary["by_error"],
                str(entry.error_text) if entry.error_text else "unknown",
            )

            parsed = parse_domain(entry.url)
            fqdn = parsed.fqdn or (entry.parsed_url.hostname or "unknown")
            self._increase_counter(summary["counts_by_fqdn"], fqdn)

        self.result["failed_requests"] = summary

    @staticmethod
    def _increase_counter(counter: CountByKey, key: str) -> None:
        normalized = key or "unknown"
        counter[normalized] = counter.get(normalized, 0) + 1
