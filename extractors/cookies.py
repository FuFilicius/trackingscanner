from datetime import datetime, timezone

from extractors.base import Extractor


class CookiesExtractor(Extractor):
    def extract_information(self):
        cookies = self.data.cookies
        scan_start_epoch = datetime.fromisoformat(self.result["scan_start"]).astimezone(
            timezone.utc
        ).timestamp()

        for cookie in cookies:
            expires = cookie.expires
            cookie.lifetime = (
                int(expires - scan_start_epoch)
                if isinstance(expires, (int, float)) and expires > 0
                else -1
            )

        self.result["cookies"] = [cookie.to_dict() for cookie in cookies]
