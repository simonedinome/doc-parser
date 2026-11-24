from pathlib import Path

from doc_parser.output.html_builder import build_html_folder, build_html_standalone


def _data() -> dict:
    return {
        "title": "Titolo Doc",
        "summary": "Sommario",
        "prerequisites": ["Req 1"],
        "procedures": [
            {
                "id": "proc_001",
                "title": "Procedura A",
                "steps": [{"number": 1, "title": "Step 1", "description": "Desc", "notes": "N", "timestamp": "00:10"}],
            }
        ],
        "glossary": [{"term": "API", "definition": "Def"}],
        "notes": ["Nota"],
    }


def test_build_html_folder_uses_relative_screenshot_path(tmp_path: Path) -> None:
    screenshot = tmp_path / "proc_001_step_001.png"
    screenshot.write_bytes(b"PNG")
    screenshot_map = {("proc_001", 1): screenshot}
    html = build_html_folder(_data(), screenshot_map, "it")
    assert 'src="screenshots/proc_001_step_001.png"' in html
    assert "Titolo Doc" in html
    assert "Prerequisiti" in html
    assert "Glossario" in html
    assert '<html lang="it">' in html


def test_build_html_standalone_embeds_base64_image(tmp_path: Path) -> None:
    screenshot = tmp_path / "proc_001_step_001.png"
    screenshot.write_bytes(b"PNG-data")
    screenshot_map = {("proc_001", 1): screenshot}
    html = build_html_standalone(_data(), screenshot_map, "it")
    assert "data:image/png;base64," in html
    assert "screenshots/" not in html


def test_build_html_english_labels() -> None:
    html = build_html_folder(_data(), {}, "en")
    assert '<html lang="en">' in html
    assert "Prerequisites" in html
    assert "Glossary" in html


def test_build_html_missing_screenshot_omits_img_tag() -> None:
    html = build_html_folder(_data(), {}, "it")
    assert "<img" not in html


def test_build_html_toc_tags_both_concepts_and_procedures() -> None:
    data = _data()
    data["concepts"] = [{"id": "con_001", "title": "Concetto X", "content": "C"}]
    html = build_html_folder(data, {}, "it")
    assert "[Concetto] Concetto X" in html
    assert "[Procedura] Procedura A" in html


def test_build_html_no_toc_tags_when_only_procedures() -> None:
    html = build_html_folder(_data(), {}, "it")
    assert "[Procedura]" not in html


def _consolidated_data() -> dict:
    data = _data()
    data["procedures"][0]["steps"][0]["source_slides"] = [4, 6]
    data["concepts"] = [{"id": "con_001", "title": "Concetto X", "content": "C", "source_slides": [2]}]
    return data


def test_build_html_shows_slide_next_to_screenshot(tmp_path: Path) -> None:
    shot = tmp_path / "proc_001_step_001.png"
    slide = tmp_path / "proc_001_step_001_slide.png"
    concept = tmp_path / "con_001_slide.png"
    for path in (shot, slide, concept):
        path.write_bytes(b"PNG")
    html = build_html_folder(
        _consolidated_data(), {("proc_001", 1): shot}, "it", {("proc_001", 1): slide}, {"con_001": concept}
    )
    assert 'class="step-images"' in html
    assert 'src="screenshots/proc_001_step_001.png"' in html
    assert 'src="screenshots/proc_001_step_001_slide.png"' in html
    assert "<figcaption>Slide 4</figcaption>" in html
    assert 'src="screenshots/con_001_slide.png"' in html and "<figcaption>Slide 2</figcaption>" in html
    assert "@media (max-width: 700px)" in html


def test_build_html_standalone_embeds_both_images(tmp_path: Path) -> None:
    shot = tmp_path / "proc_001_step_001.png"
    slide = tmp_path / "proc_001_step_001_slide.png"
    shot.write_bytes(b"PNG-a")
    slide.write_bytes(b"PNG-b")
    html = build_html_standalone(_consolidated_data(), {("proc_001", 1): shot}, "en", {("proc_001", 1): slide})
    assert html.count("data:image/png;base64,") == 2
    assert "Slide 4" in html
