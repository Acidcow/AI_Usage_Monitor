import json
import csv
import io
import time
import datetime
from typing import Dict, Any, List, Optional
from backend.storage.database import UsageDatabase

class TelemetryImporter:
    """
    Corporate Telemetry Importer & Manual Session Logger.
    Allows importing raw telemetry files (JSON, JSONL, CSV) or logging interactions
    manually for highly restricted environments (e.g. M365 Copilot).
    """

    def __init__(self, database: UsageDatabase):
        self.db = database

    def import_raw_telemetry(self, raw_content: str, default_provider: str = "copilot") -> int:
        """Parses JSON, JSONL, or CSV string and records events in database."""
        if not raw_content or not raw_content.strip():
            return 0

        text = raw_content.strip()
        ingested = 0

        # 1. Try parsing as JSON Array
        if text.startswith("["):
            try:
                items = json.loads(text)
                for it in items:
                    if self._ingest_record(it, default_provider):
                        ingested += 1
                return ingested
            except Exception:
                pass

        # 2. Try parsing as JSONL
        if text.startswith("{"):
            is_jsonl = False
            for line in text.splitlines():
                line_clean = line.strip()
                if not line_clean:
                    continue
                try:
                    it = json.loads(line_clean)
                    if self._ingest_record(it, default_provider):
                        ingested += 1
                        is_jsonl = True
                except Exception:
                    break
            if is_jsonl:
                return ingested

        # 3. Try parsing as CSV
        try:
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                if self._ingest_record(row, default_provider):
                    ingested += 1
        except Exception:
            pass

        return ingested

    def log_manual_interaction(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        session_id: Optional[str] = None,
        notes: Optional[str] = None
    ) -> str:
        """Manually records an interaction."""
        prov = provider.lower()
        evt_id = self.db.record_usage_event(
            provider=prov,
            model=model or "manual_entry",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            session_id=session_id or f"manual_{int(time.time())}"
        )
        self.db.update_provider_snapshot(
            provider=prov,
            plan_type="Enterprise Passive",
            status="ACTIVE"
        )
        return evt_id

    def _ingest_record(self, item: Dict[str, Any], default_prov: str) -> bool:
        try:
            prov = str(item.get("provider", default_prov)).lower()
            model = str(item.get("model", "default"))
            in_tok = int(item.get("input_tokens", item.get("prompt_tokens", 0)))
            out_tok = int(item.get("output_tokens", item.get("completion_tokens", 0)))
            sess_id = item.get("session_id", f"imp_{int(time.time()*1000)}")
            ts = item.get("timestamp") or datetime.datetime.now(datetime.timezone.utc).isoformat()

            self.db.record_usage_event(
                provider=prov,
                model=model,
                input_tokens=in_tok,
                output_tokens=out_tok,
                session_id=sess_id,
                recorded_at=ts
            )
            return True
        except Exception:
            return False
