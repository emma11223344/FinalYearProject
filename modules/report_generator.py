import json
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter


def generate_campaign_report(campaign, results, reports_dir):
	"""Create or update a JSON report for a campaign once enough responses exist."""
	report_directory = Path(reports_dir)
	report_directory.mkdir(parents=True, exist_ok=True)

	action_summary = Counter(result.action for result in results)
	report_payload = {
		"generated_at": datetime.now(timezone.utc).isoformat(),
		"campaign": {
			"id": campaign.id,
			"scenario": campaign.scenario,
		},
		"response_count": len(results),
		"summary": dict(action_summary),
		"responses": [
			{
				"id": result.id,
				"employee_email": result.employee_email,
				"action": result.action,
			}
			for result in results
		],
	}

	report_path = report_directory / f"campaign_{campaign.id}_report.json"
	report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
	return str(report_path)
