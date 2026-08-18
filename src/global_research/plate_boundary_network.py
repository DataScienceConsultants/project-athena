"""Connected PB2002 boundary-network geometry for retrospective research."""

from __future__ import annotations

import heapq
import math
from collections.abc import Iterable
from dataclasses import dataclass

from src.catalog.models import CatalogEvent
from src.global_research.plate_boundaries import (
    PlateBoundaryAssociation,
    PlateBoundaryStep,
)
from src.spatial.distance import (
    EARTH_RADIUS_KM,
    validate_latitude,
    validate_longitude,
)

ROUTING_SCOPES = frozenset({"all", "same_plate_pair", "same_boundary_id"})
_VECTOR_EPSILON = 1e-15
_ARC_TOLERANCE_RADIANS = 1e-9


@dataclass(frozen=True, slots=True)
class PlateBoundaryProjection:
    """Nearest point on one already-associated PB2002 digitization step."""

    event_id: str
    step_id: str
    boundary_id: str
    left_plate: str
    right_plate: str
    boundary_class: str
    projected_latitude: float
    projected_longitude: float
    distance_to_boundary_km: float
    fraction_from_start: float
    distance_from_start_km: float
    distance_to_end_km: float

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a nonempty string.")
        if not isinstance(self.step_id, str) or not self.step_id.strip():
            raise ValueError("step_id must be a nonempty string.")
        if not isinstance(self.boundary_id, str) or len(self.boundary_id) != 5:
            raise ValueError("boundary_id must be a five-character PB2002 identifier.")
        if not isinstance(self.left_plate, str) or len(self.left_plate) != 2:
            raise ValueError("left_plate must be a two-character PB2002 identifier.")
        if not isinstance(self.right_plate, str) or len(self.right_plate) != 2:
            raise ValueError("right_plate must be a two-character PB2002 identifier.")
        object.__setattr__(
            self,
            "projected_latitude",
            validate_latitude(self.projected_latitude),
        )
        object.__setattr__(
            self,
            "projected_longitude",
            validate_longitude(self.projected_longitude),
        )
        for name in (
            "distance_to_boundary_km",
            "fraction_from_start",
            "distance_from_start_km",
            "distance_to_end_km",
        ):
            value = _finite(getattr(self, name), name)
            if value < 0:
                raise ValueError(f"{name} must be nonnegative.")
            object.__setattr__(self, name, value)
        if self.fraction_from_start > 1:
            raise ValueError("fraction_from_start must be at most 1.")


@dataclass(frozen=True, slots=True)
class PlateBoundaryGraph:
    """Exact endpoint-connected graph built from PB2002 digitization steps."""

    steps: tuple[PlateBoundaryStep, ...]
    nodes: tuple[tuple[float, float], ...]
    step_nodes: dict[str, tuple[int, int]]
    component_count: int
    _step_indexes: dict[str, int]
    _adjacency: tuple[tuple[tuple[int, int, float], ...], ...]

    @classmethod
    def build(cls, steps: Iterable[PlateBoundaryStep]) -> "PlateBoundaryGraph":
        step_tuple = tuple(steps)
        if not step_tuple:
            raise ValueError("steps must contain at least one PlateBoundaryStep.")
        if not all(isinstance(step, PlateBoundaryStep) for step in step_tuple):
            raise TypeError("steps must contain PlateBoundaryStep objects.")

        node_indexes: dict[tuple[float, float], int] = {}
        nodes: list[tuple[float, float]] = []
        step_nodes: dict[str, tuple[int, int]] = {}
        step_indexes: dict[str, int] = {}
        mutable_adjacency: list[list[tuple[int, int, float]]] = []

        def node_index(coordinate: tuple[float, float]) -> int:
            existing = node_indexes.get(coordinate)
            if existing is not None:
                return existing
            index = len(nodes)
            node_indexes[coordinate] = index
            nodes.append(coordinate)
            mutable_adjacency.append([])
            return index

        for step_index, step in enumerate(step_tuple):
            if step.step_id in step_indexes:
                raise ValueError(f"Duplicate step_id: {step.step_id}")
            start_node = node_index(step.start)
            end_node = node_index(step.end)
            if start_node == end_node:
                raise ValueError(f"Step {step.step_id} has identical graph endpoints.")
            step_indexes[step.step_id] = step_index
            step_nodes[step.step_id] = (start_node, end_node)
            mutable_adjacency[start_node].append(
                (end_node, step_index, step.length_km)
            )
            mutable_adjacency[end_node].append(
                (start_node, step_index, step.length_km)
            )

        adjacency = tuple(
            tuple(sorted(neighbors, key=lambda item: (item[0], item[1])))
            for neighbors in mutable_adjacency
        )
        return cls(
            steps=step_tuple,
            nodes=tuple(nodes),
            step_nodes=step_nodes,
            component_count=_component_count(adjacency),
            _step_indexes=step_indexes,
            _adjacency=adjacency,
        )

    @property
    def edge_count(self) -> int:
        return len(self.steps)

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    def step(self, step_id: str) -> PlateBoundaryStep:
        try:
            return self.steps[self._step_indexes[step_id]]
        except KeyError as exc:
            raise KeyError(f"Unknown PB2002 step_id: {step_id}") from exc

    def distances_from_projection(
        self,
        projection: PlateBoundaryProjection,
        *,
        routing_scope: str = "same_plate_pair",
    ) -> tuple[float, ...]:
        """Return shortest graph distances from one projected event to every node."""

        _validate_projection_for_graph(projection, self)
        scope = _routing_scope(routing_scope)
        source_step = self.step(projection.step_id)
        predicate = _route_predicate(scope, source_step)
        start_node, end_node = self.step_nodes[source_step.step_id]
        distances = [math.inf] * self.node_count
        queue: list[tuple[float, int]] = []

        for node, distance in (
            (start_node, projection.distance_from_start_km),
            (end_node, projection.distance_to_end_km),
        ):
            if distance < distances[node]:
                distances[node] = distance
                heapq.heappush(queue, (distance, node))

        while queue:
            distance, node = heapq.heappop(queue)
            if distance != distances[node]:
                continue
            for neighbor, step_index, edge_length in self._adjacency[node]:
                step = self.steps[step_index]
                if not predicate(step):
                    continue
                candidate = distance + edge_length
                if candidate < distances[neighbor]:
                    distances[neighbor] = candidate
                    heapq.heappush(queue, (candidate, neighbor))
        return tuple(distances)

    def along_boundary_distance_km(
        self,
        source: PlateBoundaryProjection,
        target: PlateBoundaryProjection,
        *,
        routing_scope: str = "same_plate_pair",
    ) -> float | None:
        """Return shortest mapped distance between two boundary projections."""

        _validate_projection_for_graph(source, self)
        _validate_projection_for_graph(target, self)
        scope = _routing_scope(routing_scope)
        source_step = self.step(source.step_id)
        target_step = self.step(target.step_id)
        predicate = _route_predicate(scope, source_step)
        if not predicate(target_step):
            return None

        node_distances = self.distances_from_projection(
            source,
            routing_scope=scope,
        )
        target_start, target_end = self.step_nodes[target.step_id]
        candidates = (
            node_distances[target_start] + target.distance_from_start_km,
            node_distances[target_end] + target.distance_to_end_km,
        )
        best = min(candidates)

        if source.step_id == target.step_id:
            best = min(
                best,
                abs(source.distance_from_start_km - target.distance_from_start_km),
            )
        return None if not math.isfinite(best) else best


def project_event_to_boundary_step(
    event: CatalogEvent,
    association: PlateBoundaryAssociation,
    graph: PlateBoundaryGraph,
) -> PlateBoundaryProjection:
    """Project an event onto the minor great-circle arc of its prepared PB2002 step."""

    if not isinstance(event, CatalogEvent):
        raise TypeError("event must be CatalogEvent.")
    if not isinstance(association, PlateBoundaryAssociation):
        raise TypeError("association must be PlateBoundaryAssociation.")
    if not isinstance(graph, PlateBoundaryGraph):
        raise TypeError("graph must be PlateBoundaryGraph.")
    if association.event_id != event.event_id:
        raise ValueError("association.event_id must match event.event_id.")

    step = graph.step(association.step_id)
    if (
        association.boundary_id != step.boundary_id
        or association.left_plate != step.left_plate
        or association.right_plate != step.right_plate
        or association.boundary_class != step.boundary_class
    ):
        raise ValueError("association tectonic fields do not match the referenced step.")

    projected, fraction, distance = _project_point_to_minor_arc(
        event.latitude,
        event.longitude,
        step.start,
        step.end,
    )
    from_start = step.length_km * fraction
    return PlateBoundaryProjection(
        event_id=event.event_id,
        step_id=step.step_id,
        boundary_id=step.boundary_id,
        left_plate=step.left_plate,
        right_plate=step.right_plate,
        boundary_class=step.boundary_class,
        projected_latitude=projected[0],
        projected_longitude=projected[1],
        distance_to_boundary_km=distance,
        fraction_from_start=fraction,
        distance_from_start_km=from_start,
        distance_to_end_km=step.length_km - from_start,
    )


def project_catalog_events_to_boundaries(
    events: Iterable[CatalogEvent],
    associations: Iterable[PlateBoundaryAssociation],
    graph: PlateBoundaryGraph,
) -> tuple[PlateBoundaryProjection, ...]:
    """Project all events that already have prepared PB2002 boundary context."""

    if not isinstance(graph, PlateBoundaryGraph):
        raise TypeError("graph must be PlateBoundaryGraph.")
    context: dict[str, PlateBoundaryAssociation] = {}
    for association in associations:
        if not isinstance(association, PlateBoundaryAssociation):
            raise TypeError(
                "associations must contain PlateBoundaryAssociation objects."
            )
        if association.event_id in context:
            raise ValueError(f"Duplicate plate association: {association.event_id}")
        context[association.event_id] = association

    projections: list[PlateBoundaryProjection] = []
    for event in events:
        if not isinstance(event, CatalogEvent):
            raise TypeError("events must contain CatalogEvent objects.")
        association = context.get(event.event_id)
        if association is not None:
            projections.append(project_event_to_boundary_step(event, association, graph))
    return tuple(projections)


def _project_point_to_minor_arc(
    latitude: float,
    longitude: float,
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], float, float]:
    latitude = validate_latitude(latitude)
    longitude = validate_longitude(longitude)
    point = _unit_vector(latitude, longitude)
    start_vector = _unit_vector(*start)
    end_vector = _unit_vector(*end)
    arc_angle = _angle(start_vector, end_vector)
    if arc_angle <= _VECTOR_EPSILON:
        raise ValueError("Cannot project onto a zero-length spherical arc.")

    normal = _cross(start_vector, end_vector)
    normal_length = _norm(normal)
    if normal_length <= _VECTOR_EPSILON:
        return _nearest_endpoint_projection(point, start_vector, end_vector, start, end)

    normal = _scale(normal, 1.0 / normal_length)
    projected_raw = _subtract(point, _scale(normal, _dot(point, normal)))
    projected_length = _norm(projected_raw)
    if projected_length <= _VECTOR_EPSILON:
        return _nearest_endpoint_projection(point, start_vector, end_vector, start, end)

    projected_vector = _scale(projected_raw, 1.0 / projected_length)
    start_to_projection = _angle(start_vector, projected_vector)
    projection_to_end = _angle(projected_vector, end_vector)
    on_minor_arc = (
        abs((start_to_projection + projection_to_end) - arc_angle)
        <= _ARC_TOLERANCE_RADIANS
    )
    if not on_minor_arc:
        return _nearest_endpoint_projection(point, start_vector, end_vector, start, end)

    fraction = min(max(start_to_projection / arc_angle, 0.0), 1.0)
    coordinate = _vector_to_coordinate(projected_vector)
    distance = EARTH_RADIUS_KM * _angle(point, projected_vector)
    return coordinate, fraction, distance


def _nearest_endpoint_projection(
    point: tuple[float, float, float],
    start_vector: tuple[float, float, float],
    end_vector: tuple[float, float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[tuple[float, float], float, float]:
    start_angle = _angle(point, start_vector)
    end_angle = _angle(point, end_vector)
    if start_angle <= end_angle:
        return start, 0.0, EARTH_RADIUS_KM * start_angle
    return end, 1.0, EARTH_RADIUS_KM * end_angle


def _route_predicate(scope: str, source_step: PlateBoundaryStep):
    if scope == "all":
        return lambda step: True
    if scope == "same_boundary_id":
        return lambda step: step.boundary_id == source_step.boundary_id
    source_pair = _plate_pair(source_step)
    return lambda step: _plate_pair(step) == source_pair


def _plate_pair(step: PlateBoundaryStep) -> tuple[str, str]:
    return tuple(sorted((step.left_plate, step.right_plate)))


def _routing_scope(value: str) -> str:
    if not isinstance(value, str):
        raise TypeError("routing_scope must be a string.")
    if value not in ROUTING_SCOPES:
        raise ValueError(
            f"routing_scope must be one of {sorted(ROUTING_SCOPES)}; got {value!r}."
        )
    return value


def _validate_projection_for_graph(
    projection: PlateBoundaryProjection,
    graph: PlateBoundaryGraph,
) -> None:
    if not isinstance(projection, PlateBoundaryProjection):
        raise TypeError("projection must be PlateBoundaryProjection.")
    step = graph.step(projection.step_id)
    if (
        projection.boundary_id != step.boundary_id
        or projection.left_plate != step.left_plate
        or projection.right_plate != step.right_plate
        or projection.boundary_class != step.boundary_class
    ):
        raise ValueError("projection tectonic fields do not match its graph step.")


def _component_count(
    adjacency: tuple[tuple[tuple[int, int, float], ...], ...],
) -> int:
    visited: set[int] = set()
    count = 0
    for start in range(len(adjacency)):
        if start in visited:
            continue
        count += 1
        stack = [start]
        visited.add(start)
        while stack:
            node = stack.pop()
            for neighbor, _, _ in adjacency[node]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    stack.append(neighbor)
    return count


def _unit_vector(
    latitude: float,
    longitude: float,
) -> tuple[float, float, float]:
    latitude_radians = math.radians(validate_latitude(latitude))
    longitude_radians = math.radians(validate_longitude(longitude))
    cosine = math.cos(latitude_radians)
    return (
        cosine * math.cos(longitude_radians),
        cosine * math.sin(longitude_radians),
        math.sin(latitude_radians),
    )


def _vector_to_coordinate(
    vector: tuple[float, float, float],
) -> tuple[float, float]:
    x, y, z = vector
    latitude = math.degrees(math.atan2(z, math.hypot(x, y)))
    longitude = math.degrees(math.atan2(y, x))
    return validate_latitude(latitude), validate_longitude(longitude)


def _angle(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    cosine = min(max(_dot(left, right), -1.0), 1.0)
    cross_length = _norm(_cross(left, right))
    return math.atan2(cross_length, cosine)


def _dot(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _cross(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return (
        left[1] * right[2] - left[2] * right[1],
        left[2] * right[0] - left[0] * right[2],
        left[0] * right[1] - left[1] * right[0],
    )


def _norm(vector: tuple[float, float, float]) -> float:
    return math.sqrt(_dot(vector, vector))


def _scale(
    vector: tuple[float, float, float],
    scalar: float,
) -> tuple[float, float, float]:
    return tuple(value * scalar for value in vector)


def _subtract(
    left: tuple[float, float, float],
    right: tuple[float, float, float],
) -> tuple[float, float, float]:
    return tuple(a - b for a, b in zip(left, right, strict=True))


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")
    return result
