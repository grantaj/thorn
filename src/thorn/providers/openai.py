from __future__ import annotations

from importlib.resources import files

from openai import OpenAI

from thorn.models import AttackReport, CandidateFinding, DefenseReport, TheoremUnit


def _read_prompt(name: str) -> str:
    return files("thorn.prompts").joinpath(name).read_text(encoding="utf-8")


def _render_unit(unit: TheoremUnit) -> str:
    refs = "\n\n".join(unit.referenced_results) or "(none extracted)"
    proof = unit.proof or "(no proof environment extracted)"
    return f"""# Result
ID: {unit.identifier}
Environment: {unit.environment}
Source: {unit.statement_range.file}:
  {unit.statement_range.start_line}-{unit.statement_range.end_line}

## Statement
{unit.statement}

## Proof
{proof}

## Local preceding context
{unit.local_context or "(none)"}

## Explicitly referenced extracted results
{refs}
"""


class OpenAIProvider:
    def __init__(self, model: str = "gpt-5.6") -> None:
        self.model = model
        self.client = OpenAI()

    def attack(self, unit: TheoremUnit) -> AttackReport:
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": _read_prompt("attacker.md")},
                {"role": "user", "content": _render_unit(unit)},
            ],
            text_format=AttackReport,
        )
        if response.output_parsed is None:
            raise RuntimeError("attacker returned no structured result")
        return response.output_parsed

    def defend(self, unit: TheoremUnit, findings: list[CandidateFinding]) -> DefenseReport:
        finding_text = "\n\n".join(
            f"[{item.id}] {item.title}\n{item.explanation}\nEvidence: {item.evidence}\n"
            f"Counterexample: {item.counterexample or '(none)'}"
            for item in findings
        )
        response = self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": _read_prompt("defender.md")},
                {
                    "role": "user",
                    "content": (
                        _render_unit(unit)
                        + "\n\n# Proposed findings to defend against\n"
                        + finding_text
                    ),
                },
            ],
            text_format=DefenseReport,
        )
        if response.output_parsed is None:
            raise RuntimeError("defender returned no structured result")
        return response.output_parsed
