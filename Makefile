.PHONY: setup format lint typecheck test check audit build smoke container export-runtime verify-export
setup:
	uv sync --frozen --dev
format:
	uv run --frozen ruff format .
lint:
	uv run --frozen ruff check .
	uv run --frozen ruff format --check .
typecheck:
	uv run --frozen pyright
test:
	uv run --frozen coverage run -m unittest discover -s tests
	uv run --frozen coverage report
check: lint typecheck test verify-export build smoke
audit:
	uv audit --preview-features audit-command --locked --no-dev
build:
	uv run --frozen python -m hatchling build
smoke:
	uv run --frozen python tools/smoke_package.py
export-runtime:
	uv export --frozen --no-dev --no-emit-project --output-file requirements.runtime.txt
verify-export:
	uv run --frozen python tools/verify_export.py
container:
	docker build --tag mos-eisley:local .
	docker run --rm --network none --read-only --tmpfs /tmp mos-eisley:local --help
	python3 tools/smoke_container.py
