.PHONY: install test lint run demo clean
install:
	pip install -e ".[dev]"
test:
	pytest --cov=opspilot --cov-report=term-missing
lint:
	ruff check opspilot tests
run:
	uvicorn opspilot.main:app --reload --port 8000
demo:
	python -m opspilot.cli demo
clean:
	rm -rf .pytest_cache .ruff_cache .coverage htmlcov
