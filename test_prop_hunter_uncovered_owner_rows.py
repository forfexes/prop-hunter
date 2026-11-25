"""QA: dynamic row outlines must not mask the source arena pixels."""
import ast
from pathlib import Path
from PIL import Image, ImageDraw

def test_dynamic_owner_rows_are_outline_only():
    for family in ("ladder","builder","lottery"):
        source=Path("prop_hunter_owner_clean_"+family+".py").read_text()
        tree=ast.parse(source)
        rows=[n for n in ast.walk(tree) if isinstance(n,ast.Call)
              and isinstance(n.func,ast.Attribute) and n.func.attr=="rounded_rectangle"
              and isinstance(n.func.value,ast.Name) and n.func.value.id=="p"]
        assert rows, family
        for node in rows:
            assert not any(k.arg=="fill" for k in node.keywords), family
            outline=next(k.value for k in node.keywords if k.arg=="outline")
            color=ast.literal_eval(outline)
            tint=Image.new("RGBA",(100,50),(0,0,0,0))
            ImageDraw.Draw(tint).rounded_rectangle((5,5,95,45),radius=7,outline=color,width=1)
            assert tint.getpixel((50,25))[3]==0
