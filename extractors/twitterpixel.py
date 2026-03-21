from urllib.parse import parse_qs

from extractors.base import Extractor


class TwitterPixelExtractor(Extractor):

    def extract_information(self):
        twitter = {
            'twitter_pixel': False,
            'events': [],
        }

        events_found = set()

        for request in self.data.request_log.values():
            netloc = request.parsed_url.netloc.lower()
            url_lower = request.url.lower()
            if 'twitter' not in netloc or 'static' in url_lower:
                continue

            query = parse_qs(request.parsed_url.query, keep_blank_values=True)
            if not query:
                continue

            twitter['twitter_pixel'] = True

            for key in ('ev', 'event', 'events', 'tw_event', 'content_type'):
                value = query.get(key, [None])[0]
                if value:
                    events_found.add(str(value))

        twitter['events'] = sorted(events_found)
        self.result['twitter_pixel'] = twitter
