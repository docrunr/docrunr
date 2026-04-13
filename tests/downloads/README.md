# Sample downloads (fixtures)

Small helper to pull **real world files** for exercising markdown extraction and chunking outside the checked-in `tests/samples/` set.

## Where files go

Downloads are written under **`.data/downloads/`**, grouped by detected MIME type. Integration tests can point at this pool with `INTEGRATION_SAMPLE_SOURCE=downloads` or `--integration-sample-source=downloads` (see `tests/integration/fixtures/sample_sources.py`).

## Where they come from

The fetcher queries **open data catalogs** and collects dataset **distribution and resource URLs** that match the MIME or extension you ask for:

- **[catalog.data.gov](https://catalog.data.gov)**: CKAN `package_search`
- **[open.canada.ca](https://open.canada.ca)**: CKAN `package_search`
- **[ckan.opendata.swiss](https://opendata.swiss)**: CKAN `package_search`
- **[data.overheid.nl](https://data.overheid.nl)**: CKAN `package_search`
- **[data.europa.eu](https://data.europa.eu)**: EU Data Hub search API

Candidates are shuffled and interleaved so one catalog does not dominate.

## Run it

From the repo root (with your Python env, `uv`, or `pytest` path as you usually use):

```bash
python -m tests.downloads pdf 5
python -m tests.downloads pdf,docx,html 3 --seed 42
```

Use supported types such as `pdf`, `docx`, `pptx`, `xlsx`, `csv`, `json`, `xml`, `html`, `txt` (see `tests/downloads/models.py`).
