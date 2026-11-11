"""Render the saved query results as SVG and PNG diagrams (requires Pillow).

These are layouts of actual returned nodes and relationships, not Neo4j UI
screenshots. No database access is needed. Labels and edges come from evidence.
"""

import argparse
import html
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
WIDTH, HEIGHT = 1320, 1100
COLORS = {"ProtocolFamily": "#dbeafe", "ProtocolDeployment": "#e0e7ff",
          "Chain": "#d1fae5", "Contract": "#fef3c7", "Function": "#ffedd5",
          "Action": "#fce7f3", "Reserve": "#e0f2fe", "Token": "#dcfce7"}


def label(node):
    p, labels = node["properties"], node["labels"]
    kind = next(k for k in COLORS if k in labels)
    if kind == "ProtocolDeployment":
        title = p["key"].split(":")[0]
        detail = "Sepolia deployment" if p["chain_id"] == 11155111 else "Mainnet deployment"
    elif kind == "Chain":
        title, detail = p["name"], f"Chain ID {p['chain_id']}"
    elif kind == "Reserve":
        title, detail = p["symbol"] + " reserve", "Active reserve"
    elif kind == "Token":
        title, detail = p["symbol"], p["address"][:10] + "..." + p["address"][-6:]
    elif kind == "Contract":
        title, detail = "Aave Pool", p["address"][:10] + "..." + p["address"][-6:]
    elif kind == "Function":
        title, detail = p["name"] + "(...)", p.get("selector", "Execution function")
    else:
        title, detail = p["name"], ""
    return kind, title, detail


def positions(data, name):
    result = {}
    for n in data["nodes"]:
        kind, _, _ = label(n)
        p = n["properties"]
        if name == "aave_supply":
            xy = {"ProtocolFamily": (400, 190), "Chain": (840, 190),
                  "ProtocolDeployment": (620, 390), "Contract": (160, 630),
                  "Reserve": (1090, 630), "Function": (160, 870),
                  "Action": (620, 870), "Token": (1090, 870)}[kind]
        else:
            if kind == "ProtocolFamily":
                index = 0 if p["key"] == "aave-v3" else 4
            elif kind == "Chain":
                index = 2 if p["chain_id"] == 1 else 6
            else:
                index = {"aave-v3:1": 1, "uniswap-v3:1": 3,
                         "uniswap-v3:11155111": 5, "aave-v3:11155111": 7}[p["key"]]
            angle = math.radians(-90 + index * 45)
            xy = (660 + 495 * math.cos(angle), 550 + 350 * math.sin(angle))
        result[n["id"]] = xy
    return result


def render(data, name, output, font_path=None):
    image = Image.new("RGB", (WIDTH * 2, HEIGHT * 2), "white")
    draw = ImageDraw.Draw(image)
    font_path = font_path or next((str(p) for p in [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    ] if p.exists()), None)
    def font(size):
        return ImageFont.truetype(font_path, size * 2) if font_path else ImageFont.load_default(size=size * 2)
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}">',
           '<rect width="100%" height="100%" fill="white"/>']
    def text(x, y, value, size=16, color="#172b4d", background=False):
        value = str(value)
        if background:
            width = draw.textlength(value, font=font(size)) / 2 + 12
            draw.rectangle(((x-width/2)*2, (y-size/2-4)*2, (x+width/2)*2, (y+size/2+4)*2), fill="white")
            svg.append(f'<rect x="{x-width/2}" y="{y-size/2-4}" width="{width}" height="{size+8}" fill="white"/>')
        draw.text((x*2, y*2), value, font=font(size), fill=color, anchor="mm")
        svg.append(f'<text x="{x}" y="{y}" text-anchor="middle" dominant-baseline="central" font-family="Arial, sans-serif" font-size="{size}" fill="{color}">{html.escape(value)}</text>')
    title = "Constructed graph: protocols and deployments" if name == "overview" else "Aave V3: USDC supply relationship subgraph"
    text(660, 50, title, 28)
    text(660, 90, f"Actual query result | {len(data['nodes'])} nodes | {len(data['relationships'])} relationships | Submission snapshot", 16)
    xy = positions(data, name)
    edge_labels = []
    for edge in data["relationships"]:
        x1, y1 = xy[edge["start"]]
        x2, y2 = xy[edge["end"]]
        dx, dy = x2-x1, y2-y1
        clip = min(123/abs(dx) if dx else float("inf"), 48/abs(dy) if dy else float("inf"))
        start, end = (x1+dx*clip, y1+dy*clip), (x2-dx*clip, y2-dy*clip)
        length = math.hypot(dx, dy)
        ux, uy = dx/length, dy/length
        tip = [end, (end[0]-ux*11-uy*5, end[1]-uy*11+ux*5),
               (end[0]-ux*11+uy*5, end[1]-uy*11-ux*5)]
        draw.line([tuple(v*2 for v in start), tuple(v*2 for v in end)], fill="#52677d", width=4)
        draw.polygon([tuple(v*2 for v in point) for point in tip], fill="#52677d")
        svg.append(f'<line x1="{start[0]}" y1="{start[1]}" x2="{end[0]}" y2="{end[1]}" stroke="#52677d" stroke-width="2"/>')
        svg.append('<polygon points="'+' '.join(f'{x},{y}' for x,y in tip)+'" fill="#52677d"/>')
        lx, ly = (x1+x2)/2, (y1+y2)/2-15
        if name == "overview" and edge["type"] == "HAS_DEPLOYMENT":
            lx += 25 if dx > 0 else -25
            ly = 230 if y1 < 550 else 875
        if name == "aave_supply" and edge["type"] == "SUPPORTS_ACTION" and abs(dx) < 1:
            lx += 90
        edge_labels.append((lx, ly, edge["type"]))
    for x,y,value in edge_labels:
        text(x,y,value,13,background=True)
    for node in data["nodes"]:
        x,y = xy[node["id"]]
        kind,title,detail = label(node)
        box = ((x-123)*2,(y-48)*2,(x+123)*2,(y+48)*2)
        draw.rounded_rectangle(box,radius=20,fill=COLORS[kind],outline="#708399",width=2)
        svg.append(f'<rect x="{x-123}" y="{y-48}" width="246" height="96" rx="10" fill="{COLORS[kind]}" stroke="#708399"/>')
        text(x,y-25,kind,12)
        text(x,y,title,19)
        if detail:
            text(x,y+26,detail,13)
    text(660,1010,"Selected stored relationships; not the complete database or proof of transaction success.",15)
    text(660,1043,"See the saved verifier result for freshness checks and the query files for reproducibility.",14)
    svg.append('</svg>')
    output.mkdir(parents=True,exist_ok=True)
    (output/(name+'.svg')).write_text('\n'.join(svg)+'\n',encoding='utf-8')
    image.save(output/(name+'.png'),dpi=(240,240))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence',type=Path,default=HERE/'evidence')
    parser.add_argument('--output',type=Path,default=HERE/'figures')
    parser.add_argument('--font',help='Optional path to an installed TrueType font')
    args=parser.parse_args()
    for name in ('overview','aave_supply'):
        render(json.loads((args.evidence/(name+'.json')).read_text(encoding='utf-8')),name,args.output,args.font)


if __name__=='__main__':
    main()
