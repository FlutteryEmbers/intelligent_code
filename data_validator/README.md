# data_validator

Standalone report rendering helper.

## Usage

```bash
pip install -r data_validator/requirements.txt
python data_validator/render_reports.py --config configs/launch.yaml
```

Outputs charts under `data_validator/results/`.

## Report Visuals

- Coverage (bucket/intent/module_span/polarity) under `results/coverage/`
- Quality summaries under `results/quality/`
- Parsing stats under `results/parsing/`
- Retrieval stats under `results/retrieval/`
- Dedup summaries under `results/dedup/`
- Question type distribution under `results/coverage/`
