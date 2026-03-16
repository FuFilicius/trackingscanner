from urllib.parse import parse_qs

from extractors.base import Extractor


class FacebookPixelExtractor(Extractor):

    def extract_information(self):
        fb = {
            'facebook_pixel': False,
            'events': []
        }

        events_found = set()

        for request in self.data.request_log.values():
            netloc = request['parsed_url']['netloc']
            path = request['parsed_url']['path']
            query = parse_qs(request['parsed_url']['query'])
            ev = query.get('ev', [None])[0]

            if 'facebook' in netloc and path in {'/tr', '/tr/'} and ev:
                fb['facebook_pixel'] = True
                events_found.add(ev)

        fb['events'] = sorted(events_found)
        self.result['facebook_pixel'] = fb