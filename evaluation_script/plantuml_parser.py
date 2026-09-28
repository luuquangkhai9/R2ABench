from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class ParsedDiagram:
    nodes: List[str] = field(default_factory=list)
    leaf_nodes: List[str] = field(default_factory=list)
    edges: List[Tuple[str, str]] = field(default_factory=list)
    node_types: Dict[str, str] = field(default_factory=dict)
    aliases: Dict[str, str] = field(default_factory=dict)


class PlantUMLParser:
    """Small PlantUML component-style parser for evaluation diagnostics.

    The parser is intentionally conservative. It extracts enough structure for
    L0/L1 diagnostics without claiming to cover the entire PlantUML grammar.
    """

    _boundary_start = re.compile(
        r"^\s*(package|folder|frame|cloud|node|rectangle|component|database|queue|interface)\s+"
        r"(?:\"([^\"]+)\"|\[([^\]]+)\]|([A-Za-z_][\w.-]*))"
        r"(?:\s+as\s+([A-Za-z_][\w.-]*))?[^{]*\{\s*$",
        re.IGNORECASE,
    )
    _boundary_end = re.compile(r"^\s*}\s*$")
    _node_patterns = [
        re.compile(
            r"^\s*(component|database|queue|cloud|node|rectangle|interface)\s+"
            r"(?:\"([^\"]+)\"|\[([^\]]+)\]|([A-Za-z_][\w.-]*))"
            r"(?:\s+as\s+([A-Za-z_][\w.-]*))?",
            re.IGNORECASE,
        ),
        re.compile(
            r"^\s*\[([^\]]+)\](?:\s+as\s+([A-Za-z_][\w.-]*))?",
            re.IGNORECASE,
        ),
    ]
    _edge = re.compile(
        r"^\s*(.*?)\s*(?:<?[-.]+(?:up|down|left|right)?[-.]*>|<[-.]+|[-.]+)\s*(.*?)(?:\s*:\s*.*)?$",
        re.IGNORECASE,
    )

    def parse(self, puml_code: str) -> ParsedDiagram:
        code = self._strip_comments(puml_code)
        nodes: Dict[str, str] = {}
        explicit_nodes: set[str] = set()
        aliases: Dict[str, str] = {}
        raw_edges: List[Tuple[str, str]] = []
        boundary_stack: List[str] = []

        def full_name(name: str) -> str:
            clean = self._clean_name(name)
            prefix = "::".join(boundary_stack) if boundary_stack else "Global"
            return f"{prefix}::{clean}"

        def register_aliases(raw_name: str, canonical: str, alias: Optional[str] = None) -> None:
            clean = self._clean_name(raw_name)
            for key in {raw_name, clean, f'"{clean}"', f"[{clean}]"}:
                aliases[key] = canonical
            if alias:
                aliases[alias] = canonical

        for raw_line in code.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("@") or line.lower().startswith("skinparam"):
                continue

            boundary_match = self._boundary_start.match(line)
            if boundary_match:
                kind = boundary_match.group(1).lower()
                name = boundary_match.group(2) or boundary_match.group(3) or boundary_match.group(4)
                alias = boundary_match.group(5)
                canonical = full_name(name)
                nodes.setdefault(canonical, kind)
                register_aliases(name, canonical, alias)
                boundary_stack.append(self._clean_name(name))
                continue

            if self._boundary_end.match(line):
                if boundary_stack:
                    boundary_stack.pop()
                continue

            node_match = self._match_node(line)
            if node_match:
                kind, name, alias = node_match
                canonical = full_name(name)
                nodes.setdefault(canonical, kind)
                explicit_nodes.add(canonical)
                register_aliases(name, canonical, alias)
                continue

            edge_match = self._edge.match(line)
            if edge_match:
                src = edge_match.group(1).split(":")[0].strip()
                dst = edge_match.group(2).split(":")[0].strip()
                raw_edges.append((src, dst))

        resolved_edges = []
        for src, dst in raw_edges:
            src_name = self._resolve_endpoint(src, aliases, full_name)
            dst_name = self._resolve_endpoint(dst, aliases, full_name)
            nodes.setdefault(src_name, "implicit")
            nodes.setdefault(dst_name, "implicit")
            resolved_edges.append((src_name, dst_name))

        all_nodes = sorted(nodes)
        leaf_nodes = [
            node
            for node in all_nodes
            if node in explicit_nodes and not any(other.startswith(f"{node}::") for other in all_nodes)
        ]
        if not leaf_nodes:
            leaf_nodes = [node for node in all_nodes if not any(other.startswith(f"{node}::") for other in all_nodes)]

        return ParsedDiagram(
            nodes=all_nodes,
            leaf_nodes=sorted(leaf_nodes),
            edges=resolved_edges,
            node_types={node: nodes[node] for node in all_nodes},
            aliases=aliases,
        )

    @staticmethod
    def _strip_comments(code: str) -> str:
        code = re.sub(r"/'.*?'/", "", code, flags=re.DOTALL)
        return re.sub(r"'.*$", "", code, flags=re.MULTILINE)

    @classmethod
    def _clean_name(cls, value: str) -> str:
        return value.strip().strip('"[](){}').replace("\n", "\\n")

    @classmethod
    def _normalize_key(cls, value: str) -> str:
        clean = cls._clean_name(value).lower()
        return re.sub(r"[^a-z0-9]+", "", clean)

    @classmethod
    def semantic_key(cls, value: str) -> str:
        parts = [cls._normalize_key(part) for part in value.split("::")]
        return "::".join(part for part in parts if part)

    @classmethod
    def label_key(cls, value: str) -> str:
        return cls._normalize_key(value.split("::")[-1])

    def _match_node(self, line: str) -> Optional[Tuple[str, str, Optional[str]]]:
        for pattern in self._node_patterns:
            match = pattern.match(line)
            if not match:
                continue
            if len(match.groups()) == 5:
                kind = match.group(1).lower()
                name = match.group(2) or match.group(3) or match.group(4)
                alias = match.group(5)
                return kind, name, alias
            name = match.group(1)
            alias = match.group(2)
            return "component", name, alias
        return None

    def _resolve_endpoint(self, raw: str, aliases: Dict[str, str], full_name) -> str:
        clean = self._clean_name(raw)
        candidates = [raw, clean, f'"{clean}"', f"[{clean}]"]
        for candidate in candidates:
            if candidate in aliases:
                return aliases[candidate]
        canonical = full_name(clean)
        aliases[raw] = canonical
        aliases[clean] = canonical
        return canonical
