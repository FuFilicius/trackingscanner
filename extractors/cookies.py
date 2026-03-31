from datetime import datetime, timezone

from extractors.base import Extractor
from utils import parse_domain


class CookiesExtractor(Extractor):
    def extract_information(self):
        cookies = self.data.cookies
        scan_start_epoch = datetime.fromisoformat(self.result["scan_start"]).astimezone(
            timezone.utc
        ).timestamp()

        summary = {
            "total": 0,
            "session": 0,
            "persistent": 0,
            "http_only": 0,
            "secure": 0,
            "thirdparty": 0,
            "tracker": 0,
            "same_site": {},
            "counts_by_fqdn": {},
        }
        lifetime_sum = 0
        persistent_count = 0

        for cookie in cookies:
            summary["total"] += 1
            expires = cookie.expires
            cookie.lifetime = (
                int(expires - scan_start_epoch)
                if isinstance(expires, (int, float)) and expires > 0
                else -1
            )

            if cookie.lifetime >= 0:
                summary["persistent"] += 1
                lifetime_sum += cookie.lifetime
                persistent_count += 1
            else:
                summary["session"] += 1

            if cookie.http_only:
                summary["http_only"] += 1
            if cookie.secure:
                summary["secure"] += 1
            if cookie.is_thirdparty:
                summary["thirdparty"] += 1
            if cookie.is_tracker:
                summary["tracker"] += 1

            same_site = cookie.same_site or "unknown"
            summary["same_site"][same_site] = summary["same_site"].get(same_site, 0) + 1

            domain = cookie.domain or ""
            normalized_domain = domain[1:] if domain.startswith(".") else domain
            cookie_fqdn = parse_domain(normalized_domain).fqdn if normalized_domain else ""
            key = cookie_fqdn or normalized_domain or "unknown"
            summary["counts_by_fqdn"][key] = summary["counts_by_fqdn"].get(key, 0) + 1

        self.result["cookies"] = summary
