import asyncio
from collections.abc import AsyncIterator

from src.rag.services.extract.extractors.extractor import Segment
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.rag.services.store import StorageJob


class Extraction:
    """
    The Extraction class is responsible for orchestrating the extraction
    of text segments from files.
    """

    def __init__(self, downloader: S3FileDownloader, factory: ExtractorFactory) -> None:
        self._downloader = downloader
        self._factory = factory

    async def stream(self, job: StorageJob) -> AsyncIterator[Segment]:
        """
        Streams segments of text extracted from the file specified in the job.
        :param job: The storage job containing the file information.
        :return: An asynchronous iterator over the extracted text segments.
        """
        async with self._downloader.download(job.download_url, job.checksum) as path:
            segments = iter(self._factory.get_extractor(job.extension).extract(path))

            while (
                segment := await asyncio.to_thread(next, segments, None)
            ) is not None:
                yield segment
