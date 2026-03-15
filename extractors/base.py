from utils import ScanData


class Extractor:
    def __init__(self, result, options, data):
        self.result = result
        self.options = options
        self.data: ScanData = data

    def extract_information(self):
        raise NotImplementedError('You have to implement extract_information() in {}'.format(
            self.__class__.__name__))

    def register_javascript(self):
        pass