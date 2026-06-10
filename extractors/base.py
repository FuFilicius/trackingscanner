from utils import ScanData
from scanner_tools.results import ScanPhaseResult


class Extractor:
    def __init__(
        self,
        result: ScanPhaseResult,
        options: dict[str, object],
        data: ScanData,
    ) -> None:
        self.result: ScanPhaseResult = result
        self.options: dict[str, object] = options
        self.data: ScanData = data

    def extract_information(self) -> None:
        raise NotImplementedError('You have to implement extract_information() in {}'.format(
            self.__class__.__name__))

    def register_javascript(self) -> str | list[str] | None:
        return None
