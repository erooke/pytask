import pprint
import sys
import traceback

import click
import networkx as nx
import pytask
from pony import orm
from pytask.dag import node_and_neigbors
from pytask.dag import sort_tasks_topologically
from pytask.dag import task_and_descending_tasks
from pytask.database import State
from pytask.exceptions import NodeNotFoundError
from pytask.exceptions import ResolvingDependenciesError
from pytask.mark.structures import Mark
from pytask.report import ResolvingDependenciesReport


@pytask.hookimpl
def pytask_resolve_dependencies(session):
    """Create a directed acyclic graph (DAG) capturing dependencies between functions.

    Parameters
    ----------
    session : session
        Dictionary containing tasks.

    """
    try:
        session.dag = session.hook.pytask_resolve_dependencies_create_dag(
            tasks=session.tasks
        )
        session.hook.pytask_resolve_dependencies_validate_dag(dag=session.dag)
        session.hook.pytask_resolve_dependencies_select_execution_dag(dag=session.dag)
    except Exception:
        report = ResolvingDependenciesReport(sys.exc_info())
        session.hook.pytask_resolve_dependencies_log(session=session, report=report)
        session.resolving_dependencies_report = report

        raise ResolvingDependenciesError

    else:
        return True


@pytask.hookimpl
def pytask_resolve_dependencies_create_dag(tasks):
    dag = nx.DiGraph()

    for task in tasks:
        dag.add_node(task.name, task=task)

        for dependency in task.depends_on:
            dag.add_node(dependency.name, node=dependency)
            dag.add_edge(dependency.name, task.name)

        for product in task.produces:
            dag.add_node(product.name, node=product)
            dag.add_edge(task.name, product.name)

    return dag


@pytask.hookimpl
def pytask_resolve_dependencies_select_execution_dag(dag):
    tasks = list(sort_tasks_topologically(dag))
    visited_nodes = []
    for task_name in tasks:
        if task_name not in visited_nodes:
            have_changed = _have_task_or_neighbors_changed(task_name, dag)
            if have_changed:
                for name in task_and_descending_tasks(task_name, dag):
                    visited_nodes.append(name)
            else:
                dag.nodes[task_name]["task"].markers.append(
                    Mark("skip_unchanged", (), {})
                )


@pytask.hookimpl
def pytask_resolve_dependencies_validate_dag(dag):
    _check_if_dag_has_cycles(dag)
    _check_if_root_nodes_are_available(dag)


def _have_task_or_neighbors_changed(task_name, dag):
    return any(
        _has_node_changed(task_name, dag.nodes[node])
        for node in node_and_neigbors(dag, task_name)
    )


@orm.db_session
def _has_node_changed(task_name, node_dict):
    node = node_dict.get("task", None) or node_dict["node"]
    try:
        state = node.state()
    except NodeNotFoundError:
        return True
    try:
        state_in_db = State[task_name, node.name].state
    except orm.ObjectNotFound:
        return True

    return not state == state_in_db


def _check_if_dag_has_cycles(dag):
    try:
        cycles = nx.algorithms.cycles.find_cycle(dag)
    except nx.NetworkXNoCycle:
        pass
    else:
        raise ResolvingDependenciesError(
            "The DAG contains cycles which means a dependency is directly or "
            "implicitly a product of the same task. See the following tuples "
            "(from a to b) to see the path in the graph which defines the cycle."
            f"\n\n{pprint.pformat(cycles)}"
        )


def _check_if_root_nodes_are_available(dag):
    for node in dag.nodes:
        is_node = "node" in dag.nodes[node]
        is_without_parents = len(list(dag.predecessors(node))) == 0
        if is_node and is_without_parents:
            try:
                dag.nodes[node]["node"].state()
            except NodeNotFoundError:
                successors = list(dag.successors(node))
                raise NodeNotFoundError(
                    f"{node} is missing and a dependency of {successors}."
                )


@pytask.hookimpl
def pytask_resolve_dependencies_log(session, report):
    tm_width = session.config["terminal_width"]

    click.echo(f"{{:=^{tm_width}}}".format(" Errors during resolving dependencies "))

    traceback.print_exception(*report.exc_info)

    click.echo("")
    click.echo("=" * tm_width)
