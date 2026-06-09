"""Middleware for header-based API version resolution."""

from fastapi import Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from src.config.configs import settings


class APIVersionMiddleware(BaseHTTPMiddleware):
	"""Resolve API version from the Accept-Version header."""

	@staticmethod
	def _unprocessable_response(message: str) -> JSONResponse:
		return JSONResponse(
			status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
			content={"detail": message},
		)

	@staticmethod
	def _normalize_version(raw_version: str | None) -> str | None:
		if raw_version is None:
			return None

		version = raw_version.strip().lower()
		if version.startswith("v"):
			version = version[1:]

		return version or None

	async def dispatch(
		self, request: Request, call_next: RequestResponseEndpoint
	) -> Response:
		if request.method == "OPTIONS":
			return await call_next(request)

		path = request.url.path

		if not path.startswith(f"api/"):
			return await call_next(request)

		supported_versions = set(settings.app.SUPPORTED_VERSIONS)
		default_version = settings.app.DEFAULT_VERSION

		header_version = self._normalize_version(request.headers.get("Accept-Version"))

		requested_version = header_version or default_version

		if requested_version not in supported_versions:
			return self._unprocessable_response(
				f"Unsupported API version '{requested_version}'. "
				f"Supported versions: {', '.join(sorted(supported_versions))}."
			)

		if (header_version is not None and header_version != "1"):
			return self._unprocessable_response(
				"Accept-Version header conflicts with URL version. "
				"Use /api routes with Accept-Version or /api/v1 without conflicting header."
			)

		request.state.api_version = requested_version

		response = await call_next(request)
		response.headers["Content-Version"] = requested_version
		existing_vary = response.headers.get("Vary")
		if not existing_vary:
			response.headers["Vary"] = "Accept-Version"
		elif "accept-version" not in existing_vary.lower():
			response.headers["Vary"] = f"{existing_vary}, Accept-Version"
		return response


