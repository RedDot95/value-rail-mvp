"""Export only public Clearance signal facts for the ChatGPT task."""
import argparse
import json
from pathlib import Path
from value_rail.clearance_feed import export_feed
from value_rail.settings import Settings

parser = argparse.ArgumentParser()
parser.add_argument('--previous', type=Path)
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
previous = json.loads(args.previous.read_text()) if args.previous and args.previous.exists() else None
report = export_feed(Settings(config_path=Path('config/production.toml'), _env_file=None),previous)
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in ('offers','signal_history')}))
# Publish an error report before marking the workflow failed.
