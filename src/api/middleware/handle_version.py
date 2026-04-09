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

		api_prefix = settings.server.API_PREFIX.rstrip("/")
		legacy_v1_prefix = settings.server.API_V1_PREFIX.rstrip("/")
		path = request.url.path

		if not (path == api_prefix or path.startswith(f"{api_prefix}/")):
			return await call_next(request)

		supported_versions = set(settings.app.SUPPORTED_VERSIONS)
		default_version = settings.app.DEFAULT_VERSION

		header_version = self._normalize_version(request.headers.get("Accept-Version"))

		if path == legacy_v1_prefix or path.startswith(f"{legacy_v1_prefix}/"):
			requested_version = "1"
		else:
			requested_version = header_version or default_version

		if requested_version not in supported_versions:
			return self._unprocessable_response(
				f"Unsupported API version '{requested_version}'. "
				f"Supported versions: {', '.join(sorted(supported_versions))}."
			)

		if (
			header_version is not None
			and (path == legacy_v1_prefix or path.startswith(f"{legacy_v1_prefix}/"))
			and header_version != "1"
		):
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


