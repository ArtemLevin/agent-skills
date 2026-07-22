.PHONY: install validate test compile clean

install:
	python -m pip install -e .

validate: test compile
	python scripts/validate_skills.py

test:
	python -m unittest discover -s tests -v

compile:
	python -m compileall -q src scripts tests

clean:
	python -c "import shutil; [shutil.rmtree(p, ignore_errors=True) for p in ('build', 'dist', '.pytest_cache', '.ruff_cache')]"
