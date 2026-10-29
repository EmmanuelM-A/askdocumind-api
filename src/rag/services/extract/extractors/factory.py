from src.config.configs import settings
from src.exceptions import unprocessable_content_error
from src.rag.services.extract.extractors.docx_extractor import DocxExtractor
from src.rag.services.extract.extractors.extractor import Extractor
from src.rag.services.extract.extractors.html_extractor import HtmlExtractor
from src.rag.services.extract.extractors.pdf_extractor import PdfExtractor
from src.rag.services.extract.extractors.plain_text_extractor import PlainTextExtractor


def _normalize_extension(extension: str) -> str:
    """Lowercase an extension and add the leading dot when it is missing."""
    extension = extension.strip().lower()
    if extension and not extension.startswith("."):
        extension = f".{extension}"
    return extension


_EXTRACTORS: dict[str, type[Extractor]] = {
    # Configured code extensions come first, so a bad entry such as ".pdf"
    # cannot replace a built-in extractor. They are normalized because
    # get_extractor lowercases the extension it looks up.
    **{
        _normalize_extension(extension): PlainTextExtractor
        for extension in settings.uploads.ALLOWED_CODE_EXTENSIONS
        if extension.strip()
    },
    ".pdf": PdfExtractor,
    ".docx": DocxExtractor,
    ".html": HtmlExtractor,
    ".txt": PlainTextExtractor,
    ".md": PlainTextExtractor,
}


class ExtractorFactory:

    @staticmethod
    def get_extractor(extension: str) -> Extractor:
        """
        Factory function to retrieve the appropriate text extractor based on the
        file extension.
        """
        extension = extension.strip().lower()

        if not extension.startswith("."):
            raise unprocessable_content_error(
                message="File extension must start with a dot (e.g., '.pdf').",
                error_code="INVALID_EXTENSION_FORMAT",
                error_details={"extension": extension},
            )

        extractor_class = _EXTRACTORS.get(extension)

        if extractor_class is None:
            raise unprocessable_content_error(
                message="Unsupported file type.",
                error_code="UNSUPPORTED_EXTENSION",
                error_details={"extension": extension},
            )

        return extractor_class()
