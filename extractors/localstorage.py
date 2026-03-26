from extractors.base import Extractor
from utils import local_storage_for_page_url


class LocalStorageExtractor(Extractor):

    def extract_information(self):

        self.result["local_storage_by_origin"] = self.data.local_storage_by_origin