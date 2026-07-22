.PHONY: install validate contracts secrets test compile clean release-check

install:
	python -m pip install -e .

validate: contracts secrets test compile
	python scripts/validate_skills.py

contracts:
	python scripts/validate_release.py

secrets:
	python scripts/scan_secrets.py

release-check: validate
	python scripts/verify_reproducible_build.py

test:
	PYTHONPATH=src python -m unittest discover -s tests -v

compile:
	python -m compileall -q src scripts tests

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist', '.pytest_cache', '.ruff_cache')]"
