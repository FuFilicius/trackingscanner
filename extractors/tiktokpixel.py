from extractors.base import Extractor


class TiktokPixelExtractor(Extractor):

    def extract_information(self):
        tiktok = {
            'tiktok_pixel': False,
            'events': [],
        }

        events_found = set()

        for request in self.data.request_log.values():
            netloc = request.parsed_url.netloc.lower()
            if 'tiktok' not in netloc:
                continue

            body_json = getattr(request, 'body_json', None)
            if not isinstance(body_json, dict) or 'event' not in body_json:
                continue

            tiktok['tiktok_pixel'] = True
            event_value = body_json.get('event')
            if isinstance(event_value, list):
                for value in event_value:
                    if value:
                        events_found.add(str(value))
            elif event_value:
                events_found.add(str(event_value))

        tiktok['events'] = sorted(events_found)
        self.result['tiktok_pixel'] = tiktok

