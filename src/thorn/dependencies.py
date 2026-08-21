from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from thorn.linguistic_declarations import ProseDeclarationInventory
from thorn.models import SourceRange, TheoremUnit
from thorn.support import ProofSupportGraph
from thorn.symbols import SymbolTable
from thorn.workspace import ProjectWorkspaceFacts


class DependencyResolution(StrEnum):
    RESOLVED = "resolved"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"


class ReferenceContext(StrEnum):
    STATEMENT = "statement"
    PROOF = "proof"


class DependencyNode(BaseModel):
    identifier: str
    label: str | None = None
    environment: str
    title: str | None = None
    statement: str
    source: SourceRange

    @classmethod
    def from_unit(cls, unit: TheoremUnit) -> DependencyNode:
        return cls(
            identifier=unit.identifier,
            label=unit.label,
            environment=unit.environment,
            title=unit.title,
            statement=unit.statement,
            source=unit.statement_range,
        )


class DependencyEdge(BaseModel):
    source_identifier: str
    target_label: str
    target_identifier: str | None = None
    source: SourceRange
    context: ReferenceContext
    resolution: DependencyResolution


class DependencyGraph(BaseModel):
    """Structural references between theorem-like units in one LaTeX project."""

    nodes: list[DependencyNode] = Field(default_factory=list)
    edges: list[DependencyEdge] = Field(default_factory=list)

    def _node_map(self) -> dict[str, DependencyNode]:
        return {node.identifier: node for node in self.nodes}

    def _node_order(self) -> dict[str, int]:
        return {node.identifier: index for index, node in enumerate(self.nodes)}

    def node(self, identifier: str) -> DependencyNode:
        try:
            return self._node_map()[identifier]
        except KeyError as exc:
            raise KeyError(f"unknown dependency node {identifier!r}") from exc

    def resolved_edges(self) -> list[DependencyEdge]:
        return [
            edge
            for edge in self.edges
            if edge.resolution == DependencyResolution.RESOLVED
            and edge.target_identifier is not None
        ]

    def unresolved_edges(self) -> list[DependencyEdge]:
        return [
            edge
            for edge in self.edges
            if edge.resolution != DependencyResolution.RESOLVED
        ]

    def direct_dependency_ids(self, identifier: str) -> list[str]:
        self.node(identifier)
        order = self._node_order()
        targets = {
            edge.target_identifier
            for edge in self.resolved_edges()
            if edge.source_identifier == identifier and edge.target_identifier is not None
        }
        return sorted(targets, key=order.__getitem__)

    def reverse_dependency_ids(self, identifier: str) -> list[str]:
        self.node(identifier)
        order = self._node_order()
        sources = {
            edge.source_identifier
            for edge in self.resolved_edges()
            if edge.target_identifier == identifier
        }
        return sorted(sources, key=order.__getitem__)

    def direct_dependencies(self, identifier: str) -> list[DependencyNode]:
        nodes = self._node_map()
        return [nodes[item] for item in self.direct_dependency_ids(identifier)]

    def reverse_dependencies(self, identifier: str) -> list[DependencyNode]:
        nodes = self._node_map()
        return [nodes[item] for item in self.reverse_dependency_ids(identifier)]

    def transitive_dependency_ids(self, identifier: str) -> list[str]:
        self.node(identifier)
        order = self._node_order()
        visited: set[str] = set()
        pending = list(self.direct_dependency_ids(identifier))
        while pending:
            current = pending.pop()
            if current == identifier or current in visited:
                continue
            visited.add(current)
            pending.extend(self.direct_dependency_ids(current))
        return sorted(visited, key=order.__getitem__)

    def transitive_dependencies(self, identifier: str) -> list[DependencyNode]:
        nodes = self._node_map()
        return [nodes[item] for item in self.transitive_dependency_ids(identifier)]

    def cycles(self) -> list[list[str]]:
        """Return cyclic strongly connected components in stable project order."""

        order = self._node_order()
        adjacency = {
            node.identifier: self.direct_dependency_ids(node.identifier)
            for node in self.nodes
        }
        index = 0
        stack: list[str] = []
        on_stack: set[str] = set()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        components: list[list[str]] = []

        def strongconnect(vertex: str) -> None:
            nonlocal index
            indices[vertex] = index
            lowlinks[vertex] = index
            index += 1
            stack.append(vertex)
            on_stack.add(vertex)

            for target in adjacency[vertex]:
                if target not in indices:
                    strongconnect(target)
                    lowlinks[vertex] = min(lowlinks[vertex], lowlinks[target])
                elif target in on_stack:
                    lowlinks[vertex] = min(lowlinks[vertex], indices[target])

            if lowlinks[vertex] != indices[vertex]:
                return

            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == vertex:
                    break

            is_self_cycle = len(component) == 1 and vertex in adjacency[vertex]
            if len(component) > 1 or is_self_cycle:
                components.append(sorted(component, key=order.__getitem__))

        for node in self.nodes:
            if node.identifier not in indices:
                strongconnect(node.identifier)

        return sorted(components, key=lambda component: order[component[0]])

    def render_dependency_context(self, identifier: str) -> list[str]:
        """Render direct graph dependencies for the semantic-review prompt packet."""

        return [
            (
                f"[{node.environment} {node.identifier}] "
                f"Source: {node.source.file}:{node.source.start_line}-{node.source.end_line}\n"
                f"{node.statement}"
            )
            for node in self.direct_dependencies(identifier)
        ]


class ExtractedProject(BaseModel):
    main_file: str
    units: list[TheoremUnit] = Field(default_factory=list)
    dependency_graph: DependencyGraph
    symbol_table: SymbolTable = Field(default_factory=SymbolTable)
    proof_support_graph: ProofSupportGraph = Field(default_factory=ProofSupportGraph)
    workspace: ProjectWorkspaceFacts | None = Field(default=None, exclude=True)
    prose_declarations: ProseDeclarationInventory | None = Field(default=None, exclude=True)

    def unit(self, identifier: str) -> TheoremUnit:
        for unit in self.units:
            if unit.identifier == identifier:
                return unit
        raise KeyError(f"unknown theorem unit {identifier!r}")
