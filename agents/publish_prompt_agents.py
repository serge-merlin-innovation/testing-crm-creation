# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "azure-ai-projects>=2.3.0",
#     "azure-identity>=1.19.0",
#     # azure-ai-projects imports httpx directly in its _patch module without declaring it, and
#     # asks for an unbounded openai>=2.8.0. openai 3.x switched to httpx2 and stopped pulling
#     # httpx in, so an unconstrained resolve installs a set the SDK cannot even import. Declare
#     # the direct import and hold openai at the major the SDK ships against.
#     "httpx>=0.28.1",
#     "openai>=2.8.0,<3",
# ]
# ///
"""Publish a new version of every prompt agent defined in this directory into the Foundry project.

Run by .github/workflows/agents.yml, which resolves the project endpoint and the model deployment
name out of the compiled Bicep parameters before calling this.
"""

import argparse
import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import AzureCliCredential

REQUIRED_DEFINITION_KEYS = ("name", "description", "instructions")
SMOKE_TEST_PROMPT = "Reply with the single word: ready"


@dataclass(frozen=True)
class PromptAgent:
    definition_file: Path
    name: str
    description: str
    instructions: str


def read_prompt_agents(directory: Path) -> list[PromptAgent]:
    definition_files = sorted(directory.glob("*.toml"))
    if not definition_files:
        raise SystemExit(f"No agent definitions found in {directory}.")

    agents: list[PromptAgent] = []
    for definition_file in definition_files:
        try:
            with definition_file.open("rb") as handle:
                definition = tomllib.load(handle)
        except tomllib.TOMLDecodeError as error:
            raise SystemExit(f"{definition_file}: not valid TOML ({error}).") from error

        missing = [key for key in REQUIRED_DEFINITION_KEYS if not str(definition.get(key, "")).strip()]
        if missing:
            raise SystemExit(f"{definition_file}: missing or empty {', '.join(missing)}.")

        if "model" in definition:
            raise SystemExit(
                f"{definition_file}: remove 'model'. The model deployment name comes from "
                "infra/parameters/ai-foundry.bicepparam so the deployed model and the agent cannot drift."
            )

        agents.append(
            PromptAgent(
                definition_file=definition_file,
                name=str(definition["name"]).strip(),
                description=str(definition["description"]).strip(),
                instructions=str(definition["instructions"]).strip(),
            )
        )

    names = [agent.name for agent in agents]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise SystemExit(f"Two definitions claim the same agent name: {', '.join(duplicates)}.")

    return agents


def read_required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing environment variable: {name}.")
    return value


def confirm_agent_answers(project: AIProjectClient, agent_name: str) -> None:
    """A published agent that cannot answer is a failed publish, so prove it responds."""
    openai = project.get_openai_client(agent_name=agent_name)
    conversation = openai.conversations.create()
    response = openai.responses.create(conversation=conversation.id, input=SMOKE_TEST_PROMPT)
    if not (response.output_text or "").strip():
        raise SystemExit(f"{agent_name} published but returned an empty response.")


def append_step_summary(rows: list[str]) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not summary_file:
        return
    with open(summary_file, "a", encoding="utf-8") as handle:
        handle.write("\n".join(rows) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate every definition and report what would be published, without contacting Azure.",
    )
    arguments = parser.parse_args()

    agents = read_prompt_agents(Path(__file__).parent)

    if arguments.dry_run:
        for agent in agents:
            print(
                f"would publish {agent.name} from {agent.definition_file.name} "
                f"({len(agent.instructions)} characters of instructions)"
            )
        return 0

    project_endpoint = read_required_environment("FOUNDRY_PROJECT_ENDPOINT")
    model_deployment_name = read_required_environment("FOUNDRY_MODEL_DEPLOYMENT_NAME")
    publication_run = read_required_environment("AGENT_PUBLICATION_RUN")

    # Both CI and local use authenticate through the Azure CLI, so ask for that credential directly
    # rather than letting DefaultAzureCredential try managed identity with the client id
    # azure/login exports and burn a retry timeout on every run.
    project = AIProjectClient(endpoint=project_endpoint, credential=AzureCliCredential())

    summary_rows = ["| Agent | Version | Model | Answers |", "| --- | --- | --- | --- |"]
    for agent in agents:
        published = project.agents.create_version(
            agent_name=agent.name,
            definition=PromptAgentDefinition(
                model=model_deployment_name,
                instructions=agent.instructions,
                tools=[],
            ),
            description=agent.description,
            # create_version takes no version label; metadata is where the run identity that
            # produced this version belongs.
            metadata={"publishedByRun": publication_run},
        )
        print(f"published {published.name} version {published.version} on {model_deployment_name}")

        confirm_agent_answers(project, agent.name)
        print(f"{agent.name} answered the smoke test")
        summary_rows.append(f"| {published.name} | {published.version} | {model_deployment_name} | yes |")

    append_step_summary(summary_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
