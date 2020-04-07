from __future__ import annotations

import copy
import ast
from typing import Set

from log import logger

import vb_utils
from external.gumtree import GumTree


class Node:
    class Property:
        UNMAPPABLE = 'unmappable'
        SYNTAX_TOKEN_INTERVALS = 'syntax-tokens'

        DEF_FOR = 'def_for'
        DEF_BY = 'def_by'
        # ORDER = 'order'  # todo

    def set_property(self, prop, value):
        self._data[prop] = value

    def update_property(self, prop, value):
        self._data[prop] = vb_utils.deep_merge(self._data.get(prop), value)

    def get_property(self, prop, default=None):
        return self._data.get(prop, default)

    class Version:
        BEFORE_CHANGES = 0
        AFTER_CHANGES = 1

    def __init__(self, label, ast, /, *, version=Version.BEFORE_CHANGES):
        global _statement_cnt
        self.statement_num = _statement_cnt
        _statement_cnt += 1

        self.label = str(label)
        self.ast = ast

        self.mapped = None

        self.in_edges = set()  # todo: make protected some fields
        self.out_edges = set()

        self.gt_node = None
        self.is_changed = False
        self.version = version

        self._data = {}

    def get_definitions(self):
        defs = []
        for e in self.in_edges:
            if isinstance(e, DataEdge) and e.label == LinkType.REFERENCE:
                defs.append(e.node_from)
        return defs

    def create_edge(self, node_to, link_type):
        e = DataEdge(link_type, node_from=self, node_to=node_to)
        self.out_edges.add(e)
        node_to.in_edges.add(e)

    def has_in_edge(self, node_from, label):
        for e in self.in_edges:
            if e.node_from == node_from and e.label == label:
                return True
        return False

    def remove_in_edge(self, e):
        self.in_edges.remove(e)
        e.node_from.out_edges.remove(e)

    def remove_out_edge(self, e):
        self.out_edges.remove(e)
        e.node_to.in_edges.remove(e)

    def get_incoming_nodes(self, /, *, label=None):
        result = set()
        for e in self.in_edges:
            if not label or e.label == label:
                result.add(e.node_from)
        return result

    def get_outgoing_nodes(self, /, *, label=None):
        result = set()
        for e in self.out_edges:
            if not label or e.label == label:
                result.add(e.node_to)
        return result

    def __repr__(self):
        return f'#{self.statement_num}'


class DataNode(Node):
    class Kind:
        VARIABLE_DECL = 'variable-decl'
        VARIABLE_USAGE = 'variable-usage'
        LITERAL = 'literal'
        UNDEFINED = 'undefined'

    def __init__(self, label, ast, /, *, key=None, kind=None):
        super().__init__(label, ast)

        self.key = key
        self.kind = kind or self.Kind.UNDEFINED

    def __repr__(self):
        return f'#{self.statement_num} {self.label} <{self.kind}>'


class StatementNode(Node):
    def __init__(self, label, ast, control_branch_stack, /):
        super().__init__(label, ast)

        self.control_branch_stack = copy.copy(control_branch_stack)

        if not isinstance(self, EntryNode) and control_branch_stack:
            control, branch_kind = control_branch_stack[-1]
            if control:
                control.create_control_edge(self, branch_kind)

    @property
    def control(self):
        control, _ = self.control_branch_stack[-1]
        return control

    @property
    def branch_kind(self):
        _, branch_kind = self.control_branch_stack[-1]
        return branch_kind

    def create_control_edge(self, node_to, branch_kind, /):
        e = ControlEdge(node_from=self, node_to=node_to, branch_kind=branch_kind)
        self.out_edges.add(e)
        node_to.in_edges.add(e)

    def reset_controls(self):
        for e in copy.copy(self.in_edges):
            if isinstance(e, ControlEdge):
                self.remove_in_edge(e)

        self.control_branch_stack = []


class EmptyNode(StatementNode):
    def __init__(self, control_branch_stack, /):
        super().__init__('empty', ast, control_branch_stack)


class OperationNode(StatementNode):
    class Label:
        RETURN = 'return'
        CONTINUE = 'continue'
        BREAK = 'break'
        RAISE = 'raise'
        PASS = 'pass'
        ASSIGN = '='

    class Kind:
        COLLECTION = 'collection'
        METHOD_CALL = 'method-call'
        ASSIGN = 'assignment'
        COMPARE = 'comparision'
        RETURN = 'return'
        RAISE = 'raise'
        BREAK = 'break'
        CONTINUE = 'continue'
        SUBSCRIPT_SLICE = 'subscript-slice'
        SUBSCRIPT_INDEX = 'subscript-index'

        DUMMY = 'dummy'

        UNCLASSIFIED = 'unclassified'

    def __init__(self, label, ast, control_branch_stack, /, *, kind=None):
        super().__init__(label, ast, control_branch_stack)
        self.kind = kind or self.Kind.UNCLASSIFIED

    def __repr__(self):
        return f'#{self.statement_num} {self.label} <{self.kind}>'


class ControlNode(StatementNode):
    class Label:
        IF = 'if'
        FOR = 'for'
        TRY = 'try'
        EXCEPT = 'except'

        ALL = [IF, FOR, TRY, EXCEPT]

    def __init__(self, label, ast, control_branch_stack, /):
        super().__init__(label, ast, control_branch_stack)

    def __repr__(self):
        return f'#{self.statement_num} {self.label}'


class EntryNode(ControlNode):
    def __init__(self, ast, /):
        super().__init__('START', ast, [])


class Edge:
    def __init__(self, label, node_from, node_to):
        self.label = label
        self.node_from = node_from
        self.node_to = node_to


class ControlEdge(Edge):
    def __init__(self, /, *, node_from, node_to, branch_kind=True):
        super().__init__('control', node_from, node_to)
        self.branch_kind = branch_kind


class DataEdge(Edge):
    def __init__(self, label, node_from, node_to):  # FIXME: DO NO CONSIDER LABEL AS LINK_TYPE, DEFINE A NEW INDICATOR
        super().__init__(label, node_from, node_to)


class LinkType:
    DEFINITION = 'def'
    RECEIVER = 'recv'
    REFERENCE = 'ref'
    PARAMETER = 'para'
    CONDITION = 'cond'
    QUALIFIER = 'qual'

    # special
    MAP = 'map'
    CONTROL = 'control'

    # hidden link types
    DEPENDENCE = 'dep'


class ExtControlFlowGraph:
    def __init__(self, node=None):
        self.entry_node = None
        self.nodes: Set[Node] = set()
        self.op_nodes: Set[OperationNode] = set()

        self.var_key_to_def_nodes = {}  # key to set
        self.var_refs = set()

        self.sinks: Set[Node] = set()
        self.statement_sinks: Set[StatementNode] = set()
        self.statement_sources: Set[StatementNode] = set()

        if node:
            self.nodes.add(node)
            self.sinks.add(node)

            if isinstance(node, StatementNode):
                self.statement_sinks.add(node)
                self.statement_sources.add(node)

            if isinstance(node, OperationNode):
                self.op_nodes.add(node)

        self.changed_nodes = set()
        self.gumtree = None

    def merge_graph(self, graph):
        self.nodes = self.nodes.union(graph.nodes)
        self.op_nodes = self.op_nodes.union(graph.op_nodes)

        unresolved_refs = copy.copy(graph.var_refs)  # because we remove from set
        for ref_node in graph.var_refs:
            def_nodes = self.var_key_to_def_nodes.get(ref_node.key)
            if def_nodes:
                for def_node in def_nodes:
                    def_node.create_edge(ref_node, LinkType.REFERENCE)
                unresolved_refs.remove(ref_node)

        for sink in self.statement_sinks:
            for source in graph.statement_sources:
                sink.create_edge(source, link_type=LinkType.DEPENDENCE)

        self.sinks = graph.sinks
        self.statement_sinks = graph.statement_sinks

        self.var_refs = self.var_refs.union(unresolved_refs)
        self._merge_def_nodes(graph)

    def parallel_merge_graphs(self, graphs, op_link_type=None):
        old_sinks = copy.copy(self.sinks)
        old_statement_sinks = copy.copy(self.statement_sinks)

        self.sinks.clear()
        self.statement_sinks.clear()

        for graph in graphs:
            unresolved_refs = copy.copy(graph.var_refs)  # because we remove from set
            for ref_node in graph.var_refs:
                def_nodes = self.var_key_to_def_nodes.get(ref_node.key)
                if def_nodes:
                    for def_node in def_nodes:
                        def_node.create_edge(ref_node, LinkType.REFERENCE)
                    unresolved_refs.remove(ref_node)

            if op_link_type:
                for op_node in graph.op_nodes:
                    for sink in old_sinks:
                        if not op_node.has_in_edge(sink, op_link_type):
                            sink.create_edge(op_node, op_link_type)

            for sink in old_statement_sinks:
                for source in graph.statement_sources:
                    sink.create_edge(source, link_type=LinkType.DEPENDENCE)

            self.nodes = self.nodes.union(graph.nodes)
            self.op_nodes = self.op_nodes.union(graph.op_nodes)
            self.sinks = self.sinks.union(graph.sinks)
            self.var_refs = self.var_refs.union(graph.var_refs)

            self.statement_sinks = self.statement_sinks.union(graph.statement_sinks)
            # self.statement_sources = self.statement_sources.union(graph.statement_sources)

            self._merge_def_nodes(graph)

    def _merge_def_nodes(self, graph):  # todo: a=5, a=8, b=a makes 2 refs
        vb_utils.deep_merge_dict(self.var_key_to_def_nodes, graph.var_key_to_def_nodes)

    def add_node(self, node: Node, /, *, link_type=None):
        if link_type:
            for sink in self.sinks:
                sink.create_edge(node, link_type)

        if isinstance(node, DataNode) and node.key:
            if link_type == LinkType.DEFINITION:
                def_nodes = self.var_key_to_def_nodes.setdefault(node.key, set())
                for def_node in copy.copy(def_nodes):
                    if def_node.key == node.key:
                        def_nodes.remove(def_node)
                def_nodes.add(node)
                self.var_key_to_def_nodes[node.key] = def_nodes
            else:
                self.var_refs.add(node)

        # self.sinks.clear()
        self.sinks.add(node)
        self.nodes.add(node)

        if isinstance(node, StatementNode):
            for sink in self.statement_sinks:
                sink.create_edge(node, link_type=LinkType.DEPENDENCE)

            self.statement_sinks.clear()
            self.statement_sinks.add(node)

            if not self.statement_sources:
                self.statement_sources.add(node)

        if isinstance(node, OperationNode):
            self.op_nodes.add(node)

    def remove_node(self, node):
        for e in node.in_edges:
            e.node_from.out_edges.remove(e)

        for e in node.out_edges:
            e.node_to.in_edges.remove(e)

        node.in_edges.clear()
        node.out_edges.clear()

        self.nodes.remove(node)
        self.op_nodes.discard(node)

        self.sinks.discard(node)
        self.statement_sinks.discard(node)

    def set_entry_node(self, entry_node):
        if self.entry_node:
            raise EntryNodeDuplicated

        self.entry_node = entry_node
        self.nodes.add(entry_node)

    def map_to_gumtree(self, gt):
        self.gumtree = gt

        with open(gt.source_path, 'r+') as f:
            lr = vb_utils.LineReader(''.join(f.readlines()))

        for node in self.nodes:
            if node.get_property(Node.Property.UNMAPPABLE):
                continue

            fst = node.ast.first_token
            lst = node.ast.last_token

            line = fst.start[0]
            col = fst.start[1]

            end_line = lst.end[0]
            end_col = lst.end[1]

            pos = lr.get_pos(line, col) + 2
            length = lr.get_pos(end_line, end_col) - lr.get_pos(line, col)

            type_label = None
            if isinstance(node, DataNode):
                if isinstance(node.ast, ast.Attribute):
                    if node.kind == DataNode.Kind.VARIABLE_USAGE:
                        type_label = GumTree.TypeLabel.ATTRIBUTE_LOAD
                    elif node.kind == DataNode.Kind.VARIABLE_DECL:
                        type_label = GumTree.TypeLabel.ATTRIBUTE_STORE
                elif isinstance(node.ast, ast.arg):
                    if node.kind == DataNode.Kind.VARIABLE_DECL:
                        type_label = GumTree.TypeLabel.SIMPLE_ARG
                else:
                    if node.kind == DataNode.Kind.VARIABLE_USAGE:
                        type_label = GumTree.TypeLabel.NAME_LOAD
                    elif node.kind == DataNode.Kind.VARIABLE_DECL:
                        type_label = GumTree.TypeLabel.NAME_STORE
            elif isinstance(node, OperationNode):
                if node.kind == OperationNode.Kind.ASSIGN:
                    type_label = GumTree.TypeLabel.ASSIGN
                elif node.kind == OperationNode.Kind.METHOD_CALL:
                    type_label = GumTree.TypeLabel.METHOD_CALL

            found = gt.find_node(pos, length, type_label=type_label)
            if found:
                logger.info(f'fg node {node} is mapped to gt node {found}', show_pid=True)

                node.gt_node = found
                found.fg_node = node
            else:
                logger.warning(f'Node {node} is not mapped to any gumtree node', show_pid=True)
                raise GumtreeMappingException

        for node in gt.nodes:
            if not node.fg_node:
                logger.info(f'gt-fg mapping failed for node {node}', show_pid=True)

    @staticmethod
    def map_by_gumtree(fg1, fg2, gt_matches):
        for match in gt_matches:
            gt_src_node = fg1.gumtree.node_id_to_node[int(match.get('src'))]
            gt_dest_node = fg2.gumtree.node_id_to_node[int(match.get('dest'))]

            invalid_mapping = False
            if not gt_src_node.fg_node:
                invalid_mapping = True

            if not gt_dest_node.fg_node:
                invalid_mapping = True

            if invalid_mapping:
                continue

            fg_src_node = gt_src_node.fg_node
            fg_dest_node = gt_dest_node.fg_node

            fg_src_node.mapped = fg_dest_node
            fg_dest_node.mapped = fg_src_node

            fg_src_node.create_edge(fg_dest_node, LinkType.MAP)

    def calc_changed_nodes_by_gumtree(self):
        self.changed_nodes.clear()

        for node in self.nodes:
            if isinstance(node, EntryNode):
                continue

            if node.get_property(Node.Property.UNMAPPABLE):
                continue

            if node.gt_node.is_changed():
                self.changed_nodes.add(node)

                defs = node.get_definitions()
                for d in defs:
                    self.changed_nodes.add(d)

    def find_node_by_ast(self, ast_node):
        for node in self.nodes:
            if node.ast == ast_node:
                return node
        return None

    def find_node_by_label(self, label):
        for node in self.nodes:
            if node.label == label:
                return node
        return None


_statement_cnt = 0


class EntryNodeDuplicated(Exception):  # TODO: move outside of this file
    pass


class GumtreeMappingException(Exception):
    pass
