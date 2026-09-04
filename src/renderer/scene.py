"""P1-03 Scene Renderer: deterministic SVG rendering for VLM consumption.

Renders roads, buildings, POI, candidate boundaries, and labels into
a self-contained SVG scene. Deterministic: same input → same output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SceneConfig:
    """Rendering configuration for the scene."""

    width: int = 800
    height: int = 800
    padding: int = 40
    background_color: str = "#f8f9fa"
    road_color: str = "#adb5bd"
    road_width: float = 2.0
    building_color: str = "#e9ecef"
    building_stroke: str = "#868e96"
    building_stroke_width: float = 1.0
    boundary_color: str = "#fa5252"
    boundary_width: float = 3.0
    boundary_dash: str = "8,4"
    candidate_color: str = "#228be6"
    candidate_width: float = 2.5
    candidate_dash: str = "4,4"
    poi_color: str = "#fab005"
    label_color: str = "#343a40"
    label_font: str = "sans-serif"
    label_size: int = 12
    title_size: int = 16
    show_legend: bool = True


@dataclass
class SceneElements:
    """All elements to render in the scene."""

    roads: list[tuple[str, str]] = field(default_factory=list)  # (wkt, label)
    buildings: list[str] = field(default_factory=list)  # wkt
    boundaries: list[tuple[str, str, str]] = field(default_factory=list)  # (wkt, label, type)
    pois: list[tuple[float, float, str]] = field(default_factory=list)  # (lng, lat, label)
    candidate_boundaries: list[tuple[str, str, float]] = field(default_factory=list)  # (wkt, label, confidence)
    title: str = ""


class SceneRenderer:
    """Renders a spatial scene as SVG for VLM consumption.

    The renderer is deterministic: same input always produces the same SVG.
    """

    def __init__(self, config: Optional[SceneConfig] = None):
        self.config = config or SceneConfig()

    def render(self, elements: SceneElements) -> str:
        """Render the scene to SVG.

        Automatically determines the coordinate bounds from all elements.
        Returns a complete SVG string.
        """
        # Determine bounding box from all geometries
        bounds = self._compute_bounds(elements)
        if bounds is None:
            return self._empty_svg()

        min_lng, min_lat, max_lng, max_lat = bounds

        # Add 10% margin
        lng_margin = (max_lng - min_lng) * 0.1 or 0.01
        lat_margin = (max_lat - min_lat) * 0.1 or 0.01
        min_lng -= lng_margin
        max_lng += lng_margin
        min_lat -= lat_margin
        max_lat += lat_margin

        # Build SVG
        svg = self._build_svg(elements, min_lng, min_lat, max_lng, max_lat)
        return svg

    def _compute_bounds(
        self, elements: SceneElements
    ) -> Optional[tuple[float, float, float, float]]:
        """Compute the bounding box of all elements."""
        from shapely import wkt as _wkt

        all_coords = []

        for wkt, _ in elements.roads:
            try:
                geom = _wkt.loads(wkt)
                all_coords.extend(geom.coords if hasattr(geom, 'coords') else [])
            except Exception:
                pass

        for wkt in elements.buildings:
            try:
                geom = _wkt.loads(wkt)
                if hasattr(geom, 'exterior'):
                    all_coords.extend(list(geom.exterior.coords))
            except Exception:
                pass

        for wkt, _, _ in elements.boundaries:
            try:
                geom = _wkt.loads(wkt)
                if hasattr(geom, 'exterior'):
                    all_coords.extend(list(geom.exterior.coords))
                elif hasattr(geom, 'coords'):
                    all_coords.extend(geom.coords)
            except Exception:
                pass

        for wkt, _, _ in elements.candidate_boundaries:
            try:
                geom = _wkt.loads(wkt)
                if hasattr(geom, 'exterior'):
                    all_coords.extend(list(geom.exterior.coords))
            except Exception:
                pass

        for lng, lat, _ in elements.pois:
            all_coords.append((lng, lat))

        if not all_coords:
            return None

        lngs = [c[0] for c in all_coords]
        lats = [c[1] for c in all_coords]
        return (min(lngs), min(lats), max(lngs), max(lats))

    def _build_svg(
        self,
        elements: SceneElements,
        min_lng: float,
        min_lat: float,
        max_lng: float,
        max_lat: float,
    ) -> str:
        c = self.config
        draw_w = c.width - 2 * c.padding
        draw_h = c.height - 2 * c.padding

        lng_range = max_lng - min_lng or 0.01
        lat_range = max_lat - min_lat or 0.01

        def _x(lng: float) -> float:
            return c.padding + (lng - min_lng) / lng_range * draw_w

        def _y(lat: float) -> float:
            return c.padding + (max_lat - lat) / lat_range * draw_h

        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{c.width}" height="{c.height}" '
            f'viewBox="0 0 {c.width} {c.height}">',
            f'  <rect width="{c.width}" height="{c.height}" '
            f'fill="{c.background_color}" />',
        ]

        # Title
        if elements.title:
            parts.append(
                f'  <text x="{c.width / 2}" y="{c.padding - 10}" '
                f'text-anchor="middle" font-family="{c.label_font}" '
                f'font-size="{c.title_size}" fill="{c.label_color}" '
                f'font-weight="bold">{self._escape(elements.title)}</text>'
            )

        # 1. Roads (bottom layer)
        for wkt, label in elements.roads:
            svg_path = self._wkt_to_svg_path(wkt, _x, _y)
            if svg_path:
                parts.append(
                    f'  <path d="{svg_path}" '
                    f'stroke="{c.road_color}" stroke-width="{c.road_width}" '
                    f'fill="none" stroke-linecap="round" stroke-linejoin="round" />'
                )

        # 2. Buildings
        for wkt in elements.buildings:
            svg_path = self._wkt_to_svg_polygon(wkt, _x, _y)
            if svg_path:
                parts.append(
                    f'  <path d="{svg_path}" '
                    f'fill="{c.building_color}" stroke="{c.building_stroke}" '
                    f'stroke-width="{c.building_stroke_width}" />'
                )

        # 3. Candidate boundaries (dashed, before confirmed boundaries)
        for wkt, label, confidence in elements.candidate_boundaries:
            svg_path = self._wkt_to_svg_polygon(wkt, _x, _y)
            if svg_path:
                parts.append(
                    f'  <path d="{svg_path}" '
                    f'stroke="{c.candidate_color}" stroke-width="{c.candidate_width}" '
                    f'stroke-dasharray="{c.candidate_dash}" fill="none" />'
                )
                # Label with confidence
                centroid = self._centroid_of_wkt(wkt)
                if centroid and label:
                    cx, cy = _x(centroid[0]), _y(centroid[1])
                    parts.append(
                        f'  <text x="{cx}" y="{cy - 5}" '
                        f'text-anchor="middle" font-family="{c.label_font}" '
                        f'font-size="{c.label_size}" fill="{c.candidate_color}">'
                        f'{self._escape(label)} ({confidence:.0%})</text>'
                    )

        # 4. Confirmed boundaries (solid, prominent)
        for wkt, label, btype in elements.boundaries:
            svg_path = self._wkt_to_svg_polygon(wkt, _x, _y)
            if svg_path:
                parts.append(
                    f'  <path d="{svg_path}" '
                    f'stroke="{c.boundary_color}" stroke-width="{c.boundary_width}" '
                    f'stroke-dasharray="{c.boundary_dash}" fill="none" />'
                )
                if label:
                    centroid = self._centroid_of_wkt(wkt)
                    if centroid:
                        cx, cy = _x(centroid[0]), _y(centroid[1])
                        parts.append(
                            f'  <text x="{cx}" y="{cy}" '
                            f'text-anchor="middle" font-family="{c.label_font}" '
                            f'font-size="{c.label_size + 2}" '
                            f'fill="{c.boundary_color}" font-weight="bold">'
                            f'{self._escape(label)}</text>'
                        )

        # 5. POIs (top layer)
        for lng, lat, label in elements.pois:
            px, py = _x(lng), _y(lat)
            parts.append(
                f'  <circle cx="{px}" cy="{py}" r="5" '
                f'fill="{c.poi_color}" stroke="#fff" stroke-width="1.5" />'
            )
            if label:
                parts.append(
                    f'  <text x="{px + 8}" y="{py + 4}" '
                    f'font-family="{c.label_font}" font-size="{c.label_size}" '
                    f'fill="{c.label_color}">{self._escape(label)}</text>'
                )

        # 6. Legend
        if c.show_legend:
            parts.extend(self._build_legend())

        parts.append('</svg>')
        return "\n".join(parts)

    def _wkt_to_svg_path(
        self, wkt: str, _x, _y
    ) -> Optional[str]:
        """Convert LINESTRING WKT to SVG path data."""
        from shapely import wkt as _wkt

        try:
            geom = _wkt.loads(wkt)
            coords = list(geom.coords)
            if not coords:
                return None
            parts = []
            for i, (lng, lat) in enumerate(coords):
                x, y = _x(lng), _y(lat)
                parts.append(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}")
            return " ".join(parts)
        except Exception:
            return None

    def _wkt_to_svg_polygon(
        self, wkt: str, _x, _y
    ) -> Optional[str]:
        """Convert POLYGON/MULTIPOLYGON WKT to SVG path data."""
        from shapely import wkt as _wkt

        try:
            geom = _wkt.loads(wkt)
            if hasattr(geom, 'geoms'):  # MultiPolygon
                paths = []
                for sub in geom.geoms:
                    p = self._polygon_to_path(sub, _x, _y)
                    if p:
                        paths.append(p)
                return " ".join(paths) if paths else None
            return self._polygon_to_path(geom, _x, _y)
        except Exception:
            return None

    def _polygon_to_path(self, geom, _x, _y) -> Optional[str]:
        if not hasattr(geom, 'exterior') or geom.exterior is None:
            return None
        coords = list(geom.exterior.coords)
        if not coords:
            return None
        parts = []
        for i, (lng, lat) in enumerate(coords):
            x, y = _x(lng), _y(lat)
            parts.append(f"{'M' if i == 0 else 'L'}{x:.1f},{y:.1f}")
        parts.append("Z")
        return " ".join(parts)

    def _centroid_of_wkt(self, wkt: str) -> Optional[tuple[float, float]]:
        from shapely import wkt as _wkt
        try:
            geom = _wkt.loads(wkt)
            c = geom.centroid
            return (c.x, c.y)
        except Exception:
            return None

    def _build_legend(self) -> list[str]:
        c = self.config
        legend_x = c.width - 160
        legend_y = c.height - 140
        items = [
            (c.boundary_color, "Confirmed Boundary", c.boundary_width, c.boundary_dash),
            (c.candidate_color, "Candidate Boundary", c.candidate_width, c.candidate_dash),
            (c.road_color, "Road", c.road_width, "none"),
            (c.building_color, "Building", None, None),
            (c.poi_color, "POI", None, None),
        ]
        parts = [
            f'  <rect x="{legend_x}" y="{legend_y}" width="150" height="130" '
            f'fill="white" stroke="#dee2e6" stroke-width="1" rx="4" />',
            f'  <text x="{legend_x + 10}" y="{legend_y + 18}" '
            f'font-family="{c.label_font}" font-size="{c.label_size}" '
            f'font-weight="bold" fill="{c.label_color}">Legend</text>',
        ]
        for i, (color, label, sw, dash) in enumerate(items):
            iy = legend_y + 30 + i * 20
            if sw is not None:
                # Line style
                dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
                parts.append(
                    f'  <line x1="{legend_x + 10}" y1="{iy}" '
                    f'x2="{legend_x + 30}" y2="{iy}" '
                    f'stroke="{color}" stroke-width="{sw}"{dash_attr} />'
                )
            else:
                # Circle/building
                parts.append(
                    f'  <rect x="{legend_x + 10}" y="{iy - 5}" width="20" height="10" '
                    f'fill="{color}" stroke="#868e96" stroke-width="0.5" />'
                )
            parts.append(
                f'  <text x="{legend_x + 38}" y="{iy + 4}" '
                f'font-family="{c.label_font}" font-size="11" fill="{c.label_color}">'
                f'{label}</text>'
            )
        return parts

    def _empty_svg(self) -> str:
        c = self.config
        parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{c.width}" height="{c.height}">',
            f'  <rect width="{c.width}" height="{c.height}" '
            f'fill="{c.background_color}" />',
            f'  <text x="{c.width / 2}" y="{c.height / 2}" '
            f'text-anchor="middle" font-family="{c.label_font}" '
            f'font-size="14" fill="#868e96">No data</text>',
        ]
        if c.show_legend:  # legend is a static overlay, valid without data
            parts.extend(self._build_legend())
        parts.append('</svg>')
        return "\n".join(parts)

    @staticmethod
    def _escape(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")