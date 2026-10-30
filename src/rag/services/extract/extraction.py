import asyncio
from collections.abc import AsyncGenerator

from src.rag.services.extract.extractors.extractor import Segment
from src.rag.services.extract.extractors.factory import ExtractorFactory
from src.rag.services.extract.file_downloader import S3FileDownloader
from src.rag.services.utils import StorageJob


class Extraction:
    """
    The Extraction class is responsible for orchestrating the extraction
    of text segments from files.
    """

    def __init__(self, downloader: S3FileDownloader, factory: ExtractorFactory) -> None:
        self._downloader = downloader
        self._factory = factory

    async def stream(self, job: StorageJob) -> AsyncGenerator[Segment, None]:
        """
        Streams segments of text extracted from the file specified in the job.

        Callers that may stop early should wrap the stream in
        contextlib.aclosing, so the temp file is removed right away.

        :param job: The storage job containing the file information.
        :return: An asynchronous iterator over the extracted text segments.
        """
        # Pick the extractor first, so an unsupported file fails before
        # any bytes leave object storage.
        extractor = self._factory.get_extractor(job.extension)

        async with self._downloader.download(job.object_key, job.checksum) as path:
            segments = iter(extractor.extract(path))
            try:
                while (
                    segment := await asyncio.to_thread(next, segments, None)
                ) is not None:
                    yield segment
            finally:
                # Closes the extractor, which releases the open PDF or file.
                close = getattr(segments, "close", None)
                if close is not None:
                    try:
                        await asyncio.shield(asyncio.to_thread(close))
                    except ValueError:
                        # A canceled read is still running in its thread, so
                        # the generator cannot be closed. It ends on its own.
                        pass
