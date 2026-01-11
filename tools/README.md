# Report Renderer

Standalone report rendering helper.

## Usage

```bash
pip install -r requirements.txt
python tools/render_reports.py --config configs/launch.yaml
```

Outputs charts under `tools/results/`.

## Report Visuals

- Coverage (bucket/intent/module_span/polarity) under `tools/results/coverage/`
- Quality summaries under `tools/results/quality/`
- Parsing stats under `tools/results/parsing/`
- Retrieval stats under `tools/results/retrieval/`
- Dedup summaries under `tools/results/dedup/`
- Question type distribution under `tools/results/coverage/`
