"""
Evaluator Report Card — collects gate results across all pipeline sections
and writes a final JSON summary for debugging and audit.
"""
import json
import logging
from datetime import datetime, timezone
from src.config import OUTPUT_DIR
import os

logger = logging.getLogger(__name__)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):
            return obj.item()
        if type(obj).__name__ in ['int64', 'int32']:
            return int(obj)
        if type(obj).__name__ in ['float64', 'float32']:
            return float(obj)
        return super().default(obj)

class EvaluatorReport:
    """Collects pass/fail results from every Evaluator gate and writes a JSON report."""

    def __init__(self, topic: str = ""):
        self.topic = topic
        self.gates: dict = {}
        self.start_time = datetime.now(timezone.utc).isoformat()

    def record_gate(self, gate_name: str, passed: bool, reason: str, details: dict = None):
        """Record the result of a single gate check."""
        self.gates[gate_name] = {
            "passed": passed,
            "reason": reason,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        status_icon = "🟢 PASS" if passed else "🔴 FAIL"
        logger.info(f"Evaluator Report: [{gate_name}] {status_icon} — {reason}")

    def all_hard_gates_passed(self) -> bool:
        """Check if all hard gates (non-soft) passed."""
        hard_gates = ["topic", "script", "voice", "visuals", "mascot", "assembly", "inspector"]
        for gate in hard_gates:
            if gate in self.gates and not self.gates[gate]["passed"]:
                return False
        return True

    def get_recommendation(self) -> str:
        """Generate publish recommendation based on gate results."""
        all_passed = all(g["passed"] for g in self.gates.values())
        hard_passed = self.all_hard_gates_passed()

        if all_passed:
            return "PUBLISH"
        elif hard_passed:
            return "PUBLISH_WITH_WARNINGS"
        else:
            return "BLOCK"

    def to_dict(self) -> dict:
        """Convert report to a dictionary."""
        return {
            "timestamp": self.start_time,
            "topic": self.topic,
            "gates": self.gates,
            "recommendation": self.get_recommendation(),
            "total_gates": len(self.gates),
            "passed_gates": sum(1 for g in self.gates.values() if g["passed"]),
            "failed_gates": sum(1 for g in self.gates.values() if not g["passed"])
        }

    def write_to_file(self, path: str = None):
        """Write the report card to a JSON file."""
        if path is None:
            path = os.path.join(OUTPUT_DIR, "evaluator_report.json")
        report = self.to_dict()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False, cls=CustomJSONEncoder)
            logger.info(f"Evaluator Report written to {path}")
            logger.info(
                f"  Summary: {report['passed_gates']}/{report['total_gates']} gates passed. "
                f"Recommendation: {report['recommendation']}"
            )
        except Exception as e:
            logger.error(f"Failed to write evaluator report: {e}")

        return report

    def print_summary(self):
        """Print a human-readable summary to the log."""
        logger.info("=" * 60)
        logger.info("  EVALUATOR REPORT CARD")
        logger.info("=" * 60)
        for gate_name, result in self.gates.items():
            icon = "✅" if result["passed"] else "❌"
            logger.info(f"  {icon} {gate_name.upper():20s} — {result['reason']}")
        logger.info("-" * 60)
        rec = self.get_recommendation()
        logger.info(f"  RECOMMENDATION: {rec}")
        logger.info("=" * 60)
