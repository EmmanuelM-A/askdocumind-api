from collections.abc import AsyncIterator

from src.rag.services.extract.extractors.extractor import Segment
from src.rag.services.extract.extractor_factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader


class Extraction:

    def __init__(self, downloader: S3FileDownloader, factory: ExtractorFactory) -> None:
        self._downloader = downloader
        self._factory = factory

    async def extract(self, job: IngestJob) -> AsyncIterator[Segment]:
        pass
