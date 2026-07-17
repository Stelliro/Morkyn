from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
readme_path = ROOT / "README.md"
text = readme_path.read_text(encoding="utf-8")
start = text.find("## Interface")
end = text.find("## Highlights")
if start < 0 or end < 0:
    raise SystemExit("Could not find Interface/Highlights sections")

section = """## Interface

Screenshots from a live local Mørkyn session (this app, not another project):

| Setup | Play | Model / context health |
| --- | --- | --- |
| <img src="Media/ui-setup.png" alt="Mørkyn setup character screen" width="100%"> | <img src="Media/ui-play.png" alt="Mørkyn play view" width="100%"> | <img src="Media/ui-play-model.png" alt="Mørkyn model tab" width="100%"> |

| World setup | LLM settings | Compact mode |
| --- | --- | --- |
| <img src="Media/ui-setup-world.png" alt="Mørkyn world setup" width="100%"> | <img src="Media/ui-model-settings.png" alt="Mørkyn LLM settings" width="100%"> | <img src="Media/ui-play-compact.png" alt="Mørkyn compact mode" width="100%"> |

Brand art and interface captures live under [`Media/`](Media/).

"""
readme_path.write_text(text[:start] + section + text[end:], encoding="utf-8", newline="\n")
print("README Interface section updated")
