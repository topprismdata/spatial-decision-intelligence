"""P1-03 Scene Renderer tests."""

from src.renderer import SceneConfig, SceneElements, SceneRenderer


class TestSceneRenderer:
    def setup_method(self):
        self.renderer = SceneRenderer()

    def test_empty_scene(self):
        svg = self.renderer.render(SceneElements())
        assert svg.startswith("<svg")
        assert "No data" in svg

    def test_road_rendering(self):
        svg = self.renderer.render(SceneElements(
            roads=[("LINESTRING(0 0, 1 0)", "Main Road")],
        ))
        assert "<path" in svg
        assert "Main Road" not in svg  # Roads don't have labels
        assert svg.startswith("<svg")

    def test_building_rendering(self):
        svg = self.renderer.render(SceneElements(
            buildings=["POLYGON((0 0, 0.5 0, 0.5 0.5, 0 0.5, 0 0))"],
        ))
        assert "<path" in svg
        assert 'fill="#e9ecef"' in svg

    def test_boundary_rendering(self):
        svg = self.renderer.render(SceneElements(
            boundaries=[("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "Compound A", "CONFIRMED")],
        ))
        assert "Compound A" in svg
        assert 'stroke-dasharray="8,4"' in svg

    def test_candidate_boundary_rendering(self):
        svg = self.renderer.render(SceneElements(
            candidate_boundaries=[
                ("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "Candidate A", 0.85),
            ],
        ))
        assert "Candidate A" in svg
        assert "85%" in svg

    def test_poi_rendering(self):
        svg = self.renderer.render(SceneElements(
            pois=[(0.5, 0.5, "Entrance")],
        ))
        assert "Entrance" in svg
        assert "<circle" in svg

    def test_legend_rendering(self):
        svg = self.renderer.render(SceneElements())
        assert "Legend" in svg

    def test_legend_disabled(self):
        config = SceneConfig(show_legend=False)
        renderer = SceneRenderer(config)
        svg = renderer.render(SceneElements())
        assert "Legend" not in svg

    def test_full_scene(self):
        """Render a complete scene with all element types."""
        svg = self.renderer.render(SceneElements(
            roads=[("LINESTRING(0 0.5, 1 0.5)", "Main St")],
            buildings=["POLYGON((0.2 0.2, 0.4 0.2, 0.4 0.4, 0.2 0.4, 0.2 0.2))"],
            boundaries=[("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))", "Compound A", "CONFIRMED")],
            candidate_boundaries=[("POLYGON((0.1 0.1, 0.9 0.1, 0.9 0.9, 0.1 0.9, 0.1 0.1))", "Candidate B", 0.75)],
            pois=[(0.5, 0.5, "Center")],
            title="Test Scene",
        ))
        assert svg.startswith("<svg")
        assert "Test Scene" in svg
        assert "Compound A" in svg
        assert "Candidate B" in svg
        assert "Center" in svg
        assert "Legend" in svg
        assert svg.count("<path") >= 3

    def test_deterministic(self):
        """Same input → same output."""
        elements = SceneElements(
            roads=[("LINESTRING(0 0, 1 0)", "Road")],
            buildings=["POLYGON((0 0, 0.5 0, 0.5 0.5, 0 0.5, 0 0))"],
            pois=[(0.3, 0.3, "POI")],
        )
        svg1 = self.renderer.render(elements)
        svg2 = self.renderer.render(elements)
        assert svg1 == svg2

    def test_html_escape(self):
        svg = self.renderer.render(SceneElements(
            pois=[(0.5, 0.5, "A & B < C")],
        ))
        assert "&amp;" in svg
        assert "&lt;" in svg