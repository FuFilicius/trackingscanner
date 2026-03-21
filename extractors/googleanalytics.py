from urllib.parse import parse_qs

from extractors.base import Extractor


class GoogleAnalyticsExtractor(Extractor):

    def extract_information(self):
        ga = {
            'has_trackers': False,
            'ids': []
        }

        ids = set()

        for request in self.data.request_log.values():
            netloc = request.parsed_url.netloc.lower()
            query_str = request.parsed_url.query.lower()
            query = parse_qs(query_str)
            id = query.get('tid', [None])[0]

            if ('google-analytics' in netloc or 'stats.g.doubleclick' in netloc or 'googletagmanager' in netloc)\
                    and ('UA-' in query_str or 'G-' in query_str or 'AW-' in query_str):
                ga['has_tracker'] = True
                if id is not None:
                    ids.add(id)

        ga['ids'] = sorted(ids)
        self.result['google_analytics'] = ga